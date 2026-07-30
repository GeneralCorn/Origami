"""
LangGraph Research Agent.

Graph flow:
  retrieve -> analyze -> [save_note] -> review
                                        |
                              YES -> final_response
                              NO  -> (refine query) -> retrieve
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from prompts import ANALYZE_PROMPT, REVIEW_PROMPT, FINAL_RESPONSE_WITH_ACTIONS_PROMPT, CHAT_ONLY_INSTRUCTION, EDIT_ALLOWED_INSTRUCTION, CLASSIFY_PROMPT, FAST_FACT_PROMPT
from routes.notes import create_note_file, append_to_note
from services.rag import vector_search
from config import LOOPS_BY_ROUTE, NOTES_DIR
from services import usage
from services.llm import Budget, ModelResult, Prompt, Purpose, complete

logger = logging.getLogger(__name__)

# Fallback when a route is not in LOOPS_BY_ROUTE. Deliberately the cheapest
# useful setting: an unrecognised route is a bug, and a bug should not
# default to the most expensive policy.
DEFAULT_MAX_LOOPS = 1

# Short greetings and tokens that are always FAST_FACT without an LLM call
_FAST_FACT_TOKENS = frozenset({
    "hi", "hello", "hey", "thanks", "thank you", "ok", "okay", "sure",
    "got it", "great", "cool", "nice", "yes", "no", "yep", "nope",
})


class ResearchState(TypedDict):
    """State passed through the research agent graph."""
    messages: list[dict[str, str]]
    current_note: str
    current_query: str
    research_notes: list[str]
    retrieved_chunks: list[str]
    # True once any retrieved segment is untrusted. ARCHITECTURE_V2 section 3
    # scopes trust to the bytes, so this is set by the ingest-time provenance
    # rather than by anything the model decides.
    tainted: bool
    loop_count: int
    is_complete: bool
    final_answer: str
    events: list[dict[str, Any]]
    allow_edits: bool
    active_note_title: str
    active_note_id: str | None
    scope: list[str] | None
    # Routing
    route: str          # "fast_fact" | "normal_rag" | "deep_research"
    max_loops: int      # per-route cap passed into review_node
    # Per-turn spend permit. Shared by reference across nodes, the same way
    # research_notes already is, so complete() sees one call counter.
    budget: Budget
    # Observability accumulators
    total_input_tokens: int
    total_output_tokens: int
    total_cache_read_tokens: int
    total_cost_usd: float
    models_used: list[str]
    # Individual final response stats (for text event metadata)
    final_latency_s: float
    final_input_tokens: int
    final_output_tokens: int


def _emit_event(state: ResearchState, event_type: str, content: Any,
                meta: dict[str, Any] | None = None) -> None:
    """Append a stream event to state for the frontend to consume."""
    event: dict[str, Any] = {
        "type": event_type,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    }
    if meta:
        event["meta"] = meta
    state["events"].append(event)


def _account(state: ResearchState, result: ModelResult) -> None:
    """Fold one call's usage into the turn's running totals."""
    state["total_input_tokens"] += result.input_tokens
    state["total_output_tokens"] += result.output_tokens
    state["total_cache_read_tokens"] += result.cache_read_tokens
    state["total_cost_usd"] += result.cost_usd
    if result.model not in state["models_used"]:
        state["models_used"].append(result.model)


def _call_meta(result: ModelResult) -> dict[str, Any]:
    """Per-thought metadata for a single model call."""
    return {
        "latency_s": round(result.elapsed_s, 2),
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "model": result.model,
        "cost_usd": round(result.cost_usd, 6),
    }


def _turn_meta(
    state: ResearchState,
    total_latency_s: float,
    *,
    latency_s: float,
    input_tokens: int,
    output_tokens: int,
) -> dict[str, Any]:
    """Cumulative turn metadata attached to the final text part.

    Shared by the graph path and the fast_fact bypass. Keeping one builder
    is what stops fast_fact turns from silently reporting zero cost when a
    field is added to only one of them.
    """
    return {
        "latency_s": round(latency_s, 2),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_input_tokens": state["total_input_tokens"],
        "total_output_tokens": state["total_output_tokens"],
        "total_latency_s": round(total_latency_s, 2),
        "total_cost_usd": round(state["total_cost_usd"], 6),
        "total_calls": state["budget"].calls_made,
        "cache_read_tokens": state["total_cache_read_tokens"],
        "models": state["models_used"],
        "route": state["route"],
    }


# -- Nodes ------------------------------------------------------------------


async def retrieve_node(state: ResearchState) -> ResearchState:
    """Retrieve relevant contextualized chunks from ChromaDB."""
    t0 = time.perf_counter()
    query = state["current_query"]

    chunks = await vector_search(query, n_results=5, file_ids=state.get("scope"))
    state["retrieved_chunks"] = [c["text"] for c in chunks]
    # Taint accumulates across loops: a later clean retrieval does not
    # untaint a turn that has already read untrusted bytes.
    state["tainted"] = state.get("tainted", False) or any(
        c["prov_trust"] == "untrusted" for c in chunks
    )

    elapsed = time.perf_counter() - t0
    meta = {"latency_s": round(elapsed, 2), "input_tokens": 0, "output_tokens": 0,
            "tainted": state["tainted"]}
    if chunks:
        # Show which sources were found
        sources = list(dict.fromkeys(c["source"] for c in chunks))  # unique, ordered
        _emit_event(state, "searching", f"Reading {len(chunks)} chunks from {', '.join(sources)}", meta=meta)
    else:
        _emit_event(state, "searching", "No relevant documents found", meta=meta)

    logger.info("[LATENCY] retrieve_node: %.3fs (%d chunks)", elapsed, len(chunks))
    return state


async def analyze_node(state: ResearchState) -> ResearchState:
    """Analyze retrieved chunks and extract relevant information."""
    if not state["retrieved_chunks"]:
        logger.info("[LATENCY] analyze_node: skipped (no chunks)")
        return state

    t0 = time.perf_counter()

    chunks_text = "\n\n---\n\n".join(state["retrieved_chunks"])
    current_notes = "\n".join(f"- {n}" for n in state["research_notes"]) if state["research_notes"] else "None yet."

    prompt = Prompt.render(ANALYZE_PROMPT, {
        "current_query": state["current_query"],
        "current_notes": current_notes,
        "chunks_text": chunks_text,
        "active_notes": state["current_note"][:2000] if state["current_note"] else "No active notes.",
    })

    result = await complete(
        Purpose.ANALYZE, prompt, state["budget"], loop=state["loop_count"]
    )
    _account(state, result)
    analysis = result.text

    if "NO_RELEVANT_INFO" not in analysis:
        # Extract bullet points as individual notes
        lines = analysis.strip().split("\n")
        new_notes = [
            line.lstrip("- \u2022*").strip()
            for line in lines
            if line.strip() and len(line.strip()) > 10
        ]
        if new_notes:
            state["research_notes"].extend(new_notes)
            _emit_event(state, "note_taking", f"Extracted {len(new_notes)} findings",
                        meta=_call_meta(result))

    logger.info("[LATENCY] analyze_node total: %.3fs", time.perf_counter() - t0)
    return state


async def save_notes_node(state: ResearchState) -> ResearchState:
    """Persist research notes to a local markdown file."""
    if not state["research_notes"] or not state["allow_edits"]:
        return state

    notes_path = NOTES_DIR / "research.md"

    header = f"\n\n## Research: {state['current_query']}\n"
    header += f"*{datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
    notes_content = "\n".join(f"- {note}" for note in state["research_notes"])
    payload = header + notes_content + "\n"

    # Use run_in_executor to avoid blocking the event loop on file I/O
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _write_notes, notes_path, payload)

    return state


def _write_notes(path: Path, content: str) -> None:
    """Synchronous helper for writing notes (runs in executor)."""
    with open(path, "a") as f:
        f.write(content)


async def review_node(state: ResearchState) -> ResearchState:
    """
    Review if the research notes fully answer the user's question.
    If not, generate a refined query and loop back.
    """
    t0 = time.perf_counter()
    # Increment before comparing, so max_loops=N yields N retrieve/analyze
    # passes and N-1 review calls. The last pass needs no continue-decision,
    # and spending a Haiku call to ask whether to loop again when no budget
    # remains would be pure waste. normal_rag therefore never calls review.
    state["loop_count"] += 1

    if state["loop_count"] >= state.get("max_loops", DEFAULT_MAX_LOOPS):
        state["is_complete"] = True
        logger.info("[LATENCY] review_node: skipped (max loops reached, route=%s)", state.get("route", "?"))
        return state

    if not state["research_notes"]:
        state["is_complete"] = True
        logger.info("[LATENCY] review_node: skipped (no research notes)")
        return state

    notes_text = "\n".join(f"- {n}" for n in state["research_notes"])

    prompt = Prompt.render(REVIEW_PROMPT, {
        "original_question": state["messages"][-1]["content"] if state["messages"] else state["current_query"],
        "notes_text": notes_text,
    })

    result = await complete(
        Purpose.REVIEW, prompt, state["budget"], loop=state["loop_count"]
    )
    _account(state, result)
    review = result.text

    if "COMPLETE" in review and "INCOMPLETE" not in review:
        state["is_complete"] = True
    else:
        # Extract refined query
        refined = review.replace("INCOMPLETE:", "").strip()
        if refined and len(refined) > 5:
            state["current_query"] = refined
            _emit_event(state, "reasoning", f"Refining search: {refined}",
                        meta=_call_meta(result))
        else:
            state["is_complete"] = True

    logger.info("[LATENCY] review_node total: %.3fs (loop %d, complete=%s)",
                time.perf_counter() - t0, state["loop_count"], state["is_complete"])
    return state


def _fix_json_escapes(text: str) -> str:
    r"""Double-escape backslashes that look like LaTeX, not JSON escapes.

    LLMs put raw LaTeX (\frac, \beta, \text, \nabla …) inside JSON strings.
    JSON allows \b \f \n \r \t but these collide with LaTeX commands when
    followed by letters (e.g. \frac → \f + rac = form-feed + "rac").

    Strategy:
    1. Escape \ NOT followed by any valid JSON escape char.
    2. \b \f are almost never genuine backspace/form-feed — escape when
       followed by any letter.
    3. \n \r \t ARE common (newline, tab) — only escape when followed by a
       lowercase letter, since LaTeX commands are always lowercase (\nabla,
       \text, \rho) while genuine newlines precede uppercase or non-alpha.
    """
    # Step 1: clearly invalid JSON escapes (\p \a \l \e \s \d …)
    text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)
    # Step 2: \b \f + any letter → almost certainly LaTeX (\beta \frac)
    text = re.sub(r'\\([bf])(?=[a-zA-Z])', r'\\\\\1', text)
    # Step 3: \n \r \t + lowercase letter → likely LaTeX (\nabla \rho \text)
    text = re.sub(r'\\([nrt])(?=[a-z])', r'\\\\\1', text)
    return text


def _escape_all_backslashes_in_strings(text: str) -> str:
    r"""Nuclear fallback: double every lone backslash inside JSON string values.

    Walks the text character-by-character, tracking whether we're inside a
    quoted string. Inside strings, any `\` not already followed by another `\`
    gets doubled.
    """
    out: list[str] = []
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"' and (i == 0 or text[i - 1] != '\\'):
            in_string = not in_string
            out.append(ch)
            i += 1
        elif in_string and ch == '\\':
            # Check if already a valid JSON escape
            if i + 1 < len(text) and text[i + 1] in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'):
                out.append(ch)         # keep the backslash
                out.append(text[i + 1])  # keep the escape char
                i += 2
            else:
                out.append('\\\\')  # double it
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _try_parse_json(text: str) -> dict | None:
    """Try json.loads with progressively aggressive escape fixing."""
    # 1. Raw attempt
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2. Regex-based fix (handles most LaTeX)
    try:
        return json.loads(_fix_json_escapes(text))
    except json.JSONDecodeError:
        pass
    # 3. Nuclear: escape every lone backslash inside string values
    try:
        return json.loads(_escape_all_backslashes_in_strings(text))
    except json.JSONDecodeError:
        return None


def _walk_json_string(text: str, start: int) -> tuple[str, int]:
    """Walk from position *after* opening `"` and return (value, end_pos).

    Handles LaTeX-polluted escaping: \\b/\\f followed by a letter are treated
    as LaTeX (\\beta, \\frac) rather than backspace/form-feed.
    """
    i = start
    chars: list[str] = []
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt == '"':   chars.append('"');  i += 2
            elif nxt == '\\': chars.append('\\'); i += 2
            elif nxt == '/':  chars.append('/');  i += 2
            elif nxt == 'n':  chars.append('\n'); i += 2
            elif nxt == 'r':  chars.append('\r'); i += 2
            elif nxt == 't':  chars.append('\t'); i += 2
            elif nxt in ('b', 'f') and i + 2 < len(text) and text[i + 2].isalpha():
                # LaTeX (\beta, \frac) — keep the backslash + letter
                chars.append('\\'); chars.append(nxt); i += 2
            elif nxt == 'b':  chars.append('\b'); i += 2
            elif nxt == 'f':  chars.append('\f'); i += 2
            else:
                # Unknown escape — keep as-is (LaTeX like \eta, \alpha …)
                chars.append('\\'); chars.append(nxt); i += 2
        elif ch == '"':
            return ''.join(chars), i + 1
        else:
            chars.append(ch); i += 1
    return ''.join(chars), i


def _regex_extract_fields(text: str) -> dict | None:
    r"""Last-resort field extraction from broken JSON via character walking.

    Handles LaTeX-polluted JSON where \frac contains \f (form-feed) and
    \beta contains \b (backspace) — ambiguities that make json.loads fail.
    """
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end <= start:
        return None
    text = text[start:end + 1]

    fields: dict[str, str] = {}
    for key in ("action", "message", "filename", "content"):
        pattern = re.compile(rf'"{key}"\s*:\s*"')
        match = pattern.search(text)
        if not match:
            continue
        value, _ = _walk_json_string(text, match.end())
        fields[key] = value

    if "action" in fields and "message" in fields:
        return fields
    return None


def _extract_json(text: str) -> tuple[dict | None, str]:
    """Extract a JSON object from LLM output, tolerating extra text or fences.

    Returns the payload and which strategy recovered it. The strategy is
    recorded per turn: how often the main answer path needs repair is the
    measurement that decides whether a cheaper model can be trusted here.
    """
    text = text.strip()

    # Direct parse
    result = _try_parse_json(text)
    if result is not None:
        return result, "direct"

    # Strip markdown code fences
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        result = _try_parse_json(m.group(1).strip())
        if result is not None:
            return result, "fence"

    # Find outermost { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        result = _try_parse_json(text[start : end + 1])
        if result is not None:
            return result, "braces"

    # Final fallback: regex field extraction (handles LaTeX/JSON escape collisions)
    result = _regex_extract_fields(text)
    if result is not None:
        return result, "regex"

    return None, "failed"


async def final_response_node(state: ResearchState) -> ResearchState:
    """Synthesize a final answer from all research notes + conversation context."""
    t0 = time.perf_counter()

    notes_text = "\n".join(f"- {n}" for n in state["research_notes"]) if state["research_notes"] else "No specific research findings."
    history = "\n".join(f"{m['role']}: {m['content']}" for m in state["messages"][-6:])
    active_notes = state["current_note"][:2000] if state["current_note"] else "No active notes."

    active_title = state["active_note_title"] or "Untitled"
    mode_instruction = (
        EDIT_ALLOWED_INSTRUCTION.format(active_note_title=active_title)
        if state["allow_edits"]
        else CHAT_ONLY_INSTRUCTION
    )

    # str.replace rather than str.format: the template carries literal JSON
    # braces, which format would read as placeholders.
    prompt = Prompt.render(
        FINAL_RESPONSE_WITH_ACTIONS_PROMPT,
        {
            "history": history,
            "notes_text": notes_text,
            "active_notes": active_notes,
            "active_note_title": active_title,
            "mode_instruction": mode_instruction,
        },
        mode="replace",
    )

    result = await complete(
        Purpose.FINAL_RESPONSE,
        prompt,
        state["budget"],
        loop=state["loop_count"],
        has_notes=bool(state["research_notes"]),
    )
    _account(state, result)
    state["final_latency_s"] = round(result.elapsed_s, 2)
    state["final_input_tokens"] = result.input_tokens
    state["final_output_tokens"] = result.output_tokens

    _emit_event(state, "reasoning", "Generated response", meta=_call_meta(result))

    raw = result.text

    if not raw.strip():
        if state["research_notes"]:
            notes_summary = "; ".join(state["research_notes"][:5])
            state["final_answer"] = f"Based on your notes, here's what I found: {notes_summary}"
        else:
            state["final_answer"] = "I couldn't find specific information about that. Could you rephrase?"
        return state

    data, json_strategy = _extract_json(raw)
    await usage.record_json_strategy(state["budget"].turn_id, result.model, json_strategy)

    if not data:
        # JSON extraction failed — treat entire response as plain chat
        logger.warning("JSON extraction failed, sending raw text: %s", raw[:200])
        state["final_answer"] = raw
        return state

    action = data.get("action", "chat")
    message = data.get("message", "")
    content = data.get("content", "")
    filename = data.get("filename", "")

    logger.debug("Parsed LLM response: action=%s, filename=%s, content_len=%d, allow_edits=%s",
                 action, filename, len(content), state["allow_edits"])

    state["final_answer"] = message

    if action in ("edit", "create") and content and state["allow_edits"]:
        try:
            if action == "create":
                title = filename.replace(".md", "") if filename else "Untitled"
                result = create_note_file(title)
                append_to_note(result["id"], content)
                logger.info("Created note %s and wrote %d chars", result["id"], len(content))
                _emit_event(state, "action", {
                    "action": "create_new",
                    "note_id": result["id"],
                    "title": title,
                    "filename": filename,
                    "markdown": content,
                    "updated_at": result["updated_at"],
                })
            elif action == "edit":
                note_id = state.get("active_note_id")
                if note_id:
                    result = append_to_note(note_id, content)
                    logger.info("Appended %d chars to note %s", len(content), note_id)
                    _emit_event(state, "action", {
                        "action": "edit_current",
                        "note_id": note_id,
                        "title": result["title"],
                        "filename": filename,
                        "markdown": content,
                        "updated_at": result["updated_at"],
                    })
                else:
                    logger.warning("Edit action but no active_note_id — skipping write")
        except Exception:
            logger.exception("Failed to write note for action=%s", action)
    elif action in ("edit", "create") and not state["allow_edits"]:
        logger.debug("Action %s suppressed: allow_edits is False", action)

    logger.info("[LATENCY] final_response_node total: %.3fs (action=%s)", time.perf_counter() - t0, action)
    return state


# -- Routing ----------------------------------------------------------------


async def classify_query(
    query: str,
    history: str,
    note_preview: str,
    budget: Budget,
) -> str:
    """Classify query into fast_fact | normal_rag | deep_research.

    Uses cheap heuristics first, falls back to Haiku for ambiguous cases.
    Returns one of: 'fast_fact', 'normal_rag', 'deep_research'.

    Takes the turn's budget so the classifier's own tokens are recorded
    against the turn it classifies. They used to be discarded entirely,
    which understated every turn by one Haiku call.
    """
    q = query.strip().lower()

    # Heuristic: obvious conversational tokens. Matched on the exact token
    # only. A "len(q) < 12" disjunct used to live here, which sent every
    # short question ("why NaN?", "fix eq 3?") down the no-retrieval path,
    # so the user's own documents were never consulted. It also inflated
    # the apparent fast_fact share, which is the numerator of every saving
    # this pipeline could claim.
    if q.rstrip(".!?,").strip() in _FAST_FACT_TOKENS:
        logger.info("[ROUTE] heuristic → fast_fact (greeting)")
        return "fast_fact"

    # Heuristic: explicit deep-research keywords
    deep_keywords = ("compare", "synthesize", "across all", "literature", "comprehensive", "all papers")
    if any(k in q for k in deep_keywords):
        logger.info("[ROUTE] heuristic → deep_research (keyword match)")
        return "deep_research"

    # LLM classifier for everything else
    prompt = Prompt.render(CLASSIFY_PROMPT, {
        "history": history,
        "note_preview": note_preview[:500],
        "query": query,
    })
    result = await complete(Purpose.CLASSIFY, prompt, budget)
    text = result.text.strip().upper()
    logger.info("[ROUTE] LLM classifier → %s (%.3fs)", text, result.elapsed_s)

    if "FAST_FACT" in text:
        return "fast_fact"
    if "DEEP_RESEARCH" in text:
        return "deep_research"
    return "normal_rag"


async def _stream_fast_fact(
    query: str,
    history: str,
    note: str,
    state: ResearchState,
):
    """Bypass retrieval entirely — answer directly from context using Haiku."""
    note_section = f"User's current note:\n{note[:1500]}\n" if note.strip() else ""
    prompt = Prompt.render(FAST_FACT_PROMPT, {
        "history": history,
        "note_section": note_section,
        "query": query,
    })

    t_pipeline = time.perf_counter()
    result = await complete(Purpose.FAST_FACT, prompt, state["budget"])
    _account(state, result)

    yield {
        "type": "text",
        "content": result.text or "I couldn't generate a response.",
        "meta": _turn_meta(
            state,
            time.perf_counter() - t_pipeline,
            latency_s=result.elapsed_s,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        ),
    }


# -- Graph ------------------------------------------------------------------


def _should_continue(state: ResearchState) -> str:
    """Route after review: loop back to retrieve or proceed to final response."""
    if state["is_complete"]:
        return "final_response"
    return "retrieve"


def build_research_graph() -> StateGraph:
    """Build and compile the LangGraph research agent."""
    graph = StateGraph(ResearchState)

    # Add nodes
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("save_notes", save_notes_node)
    graph.add_node("review", review_node)
    graph.add_node("final_response", final_response_node)

    # Define edges
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "analyze")
    graph.add_edge("analyze", "save_notes")
    graph.add_edge("save_notes", "review")
    graph.add_conditional_edges("review", _should_continue, {
        "retrieve": "retrieve",
        "final_response": "final_response",
    })
    graph.add_edge("final_response", END)

    return graph.compile()


# Compiled graph — reuse across requests
research_agent = build_research_graph()




async def _prepare_turn(
    messages: list[dict[str, str]],
    current_note: str,
) -> tuple[str, str, str, int, Budget]:
    """Resolve the user query, history window, route, and per-turn budget.

    Runs before the graph so the classifier's own tokens land on the same
    turn_id as the rest of the turn.
    """
    user_query = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_query = msg["content"]
            break

    history = "\n".join(f"{m['role']}: {m['content']}" for m in messages[-3:])

    budget = Budget.interactive()
    route = await classify_query(user_query, history, current_note, budget)
    max_loops = LOOPS_BY_ROUTE.get(route, DEFAULT_MAX_LOOPS)
    budget.adopt_route(route, max_loops)

    return user_query, history, route, max_loops, budget


def _initial_state(
    messages: list[dict[str, str]],
    current_note: str,
    user_query: str,
    route: str,
    max_loops: int,
    budget: Budget,
    allow_edits: bool,
    active_note_title: str,
    active_note_id: str | None,
    scope: list[str] | None,
) -> ResearchState:
    return {
        "messages": messages,
        "current_note": current_note,
        "current_query": user_query,
        "research_notes": [],
        "retrieved_chunks": [],
        "tainted": False,
        "loop_count": 0,
        "is_complete": False,
        "final_answer": "",
        "events": [],
        "allow_edits": allow_edits,
        "active_note_title": active_note_title,
        "active_note_id": active_note_id,
        "scope": scope,
        "route": route,
        "max_loops": max_loops,
        "budget": budget,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_cache_read_tokens": 0,
        "total_cost_usd": 0.0,
        "models_used": [],
        "final_latency_s": 0.0,
        "final_input_tokens": 0,
        "final_output_tokens": 0,
    }


async def stream_research_agent(
    messages: list[dict[str, str]],
    current_note: str = "",
    allow_edits: bool = False,
    active_note_title: str = "",
    active_note_id: str | None = None,
    scope: list[str] | None = None,
):
    """
    Stream the research agent execution, yielding events as they occur.

    Yields dicts with:
        {"type": "searching"|"reasoning"|"note_taking"|"text"|"action", "content": ...}
    """
    user_query, history, route, max_loops, budget = await _prepare_turn(messages, current_note)

    state = _initial_state(
        messages, current_note, user_query, route, max_loops, budget,
        allow_edits, active_note_title, active_note_id, scope,
    )

    # Fast-fact: skip the graph entirely
    if route == "fast_fact":
        async for event in _stream_fast_fact(user_query, history, current_note, state):
            yield event
        return

    last_event_count = 0
    total_cost = 0.0
    t_pipeline = time.perf_counter()
    logger.info("[ROUTE] %s → max_loops=%d, max_calls=%d", route, max_loops, budget.max_calls)

    # max_loops is enforced in exactly one place, review_node. If that node
    # ever raises or is bypassed, the graph would loop to LangGraph's
    # default recursion_limit of 25 instead — roughly eight unbudgeted
    # analyze passes. Each loop is four nodes (retrieve, analyze,
    # save_notes, review) plus one final_response superstep, so this is the
    # route's own shape with one superstep of headroom.
    config = {"recursion_limit": 4 * max_loops + 2}

    async for state_update in research_agent.astream(state, config=config):
        # Each state_update is a dict of {node_name: updated_state}
        for node_name, node_state in state_update.items():
            if node_name == "__end__":
                continue

            t_node_done = time.perf_counter()
            logger.info("[LATENCY] node '%s' completed at +%.3fs", node_name, t_node_done - t_pipeline)

            # LangGraph hands each node a copy of the state dict, so a
            # scalar written by a node is only visible on what it yields.
            total_cost = node_state.get("total_cost_usd", total_cost)

            events = node_state.get("events", [])
            # Yield any new events since last check
            for event in events[last_event_count:]:
                yield event
            last_event_count = len(events)

            # If we have a final answer, yield it as text with stats
            if node_state.get("final_answer"):
                yield {
                    "type": "text",
                    "content": node_state["final_answer"],
                    "meta": _turn_meta(
                        node_state,
                        time.perf_counter() - t_pipeline,
                        latency_s=node_state.get("final_latency_s", 0.0),
                        input_tokens=node_state.get("final_input_tokens", 0),
                        output_tokens=node_state.get("final_output_tokens", 0),
                    ),
                }

    logger.info("[LATENCY] === pipeline total: %.3fs, %d calls, $%.6f ===",
                time.perf_counter() - t_pipeline, budget.calls_made, total_cost)
