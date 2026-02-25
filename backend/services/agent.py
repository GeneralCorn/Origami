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
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END

from prompts import ANALYZE_PROMPT, REVIEW_PROMPT, FINAL_RESPONSE_WITH_ACTIONS_PROMPT, CHAT_ONLY_INSTRUCTION, EDIT_ALLOWED_INSTRUCTION
from routes.notes import create_note_file, append_to_note
from services.rag import vector_search
from services.text_utils import strip_think_tags

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
NOTES_DIR = _BACKEND_DIR / "notes"
NOTES_DIR.mkdir(exist_ok=True)

AGENT_MODEL = "deepseek-r1:7b"
MAX_RESEARCH_LOOPS = 3


class ResearchState(TypedDict):
    """State passed through the research agent graph."""
    messages: list[dict[str, str]]
    current_note: str
    current_query: str
    research_notes: list[str]
    retrieved_chunks: list[str]
    loop_count: int
    is_complete: bool
    final_answer: str
    events: list[dict[str, Any]]
    allow_edits: bool
    active_note_title: str
    active_note_id: str | None
    scope: list[str] | None


def _emit_event(state: ResearchState, event_type: str, content: Any) -> None:
    """Append a stream event to state for the frontend to consume."""
    state["events"].append({
        "type": event_type,
        "content": content,
        "timestamp": datetime.now().isoformat(),
    })


# -- Nodes ------------------------------------------------------------------


async def retrieve_node(state: ResearchState) -> ResearchState:
    """Retrieve relevant contextualized chunks from ChromaDB."""
    query = state["current_query"]

    chunks = await vector_search(query, n_results=5, file_ids=state.get("scope"))
    state["retrieved_chunks"] = [c["text"] for c in chunks]

    if chunks:
        # Show which sources were found
        sources = list(dict.fromkeys(c["source"] for c in chunks))  # unique, ordered
        _emit_event(state, "searching", f"Reading {len(chunks)} chunks from {', '.join(sources)}")
    else:
        _emit_event(state, "searching", "No relevant documents found")

    return state


async def analyze_node(state: ResearchState) -> ResearchState:
    """Analyze retrieved chunks and extract relevant information."""
    if not state["retrieved_chunks"]:
        return state

    llm = ChatOllama(model=AGENT_MODEL, temperature=0, num_predict=2048)

    chunks_text = "\n\n---\n\n".join(state["retrieved_chunks"])
    current_notes = "\n".join(f"- {n}" for n in state["research_notes"]) if state["research_notes"] else "None yet."

    prompt = ANALYZE_PROMPT.format(
        current_query=state["current_query"],
        current_notes=current_notes,
        chunks_text=chunks_text,
        active_notes=state["current_note"][:2000] if state["current_note"] else "No active notes.",
    )

    response = await llm.ainvoke(prompt)
    analysis = response.content
    if isinstance(analysis, str):
        analysis = strip_think_tags(analysis)

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
            _emit_event(state, "note_taking", f"Extracted {len(new_notes)} findings")

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
    state["loop_count"] += 1

    if state["loop_count"] >= MAX_RESEARCH_LOOPS:
        state["is_complete"] = True
        return state

    if not state["research_notes"]:
        state["is_complete"] = True
        return state

    llm = ChatOllama(model=AGENT_MODEL, temperature=0, num_predict=1024)
    notes_text = "\n".join(f"- {n}" for n in state["research_notes"])

    prompt = REVIEW_PROMPT.format(
        original_question=state["messages"][-1]["content"] if state["messages"] else state["current_query"],
        notes_text=notes_text,
    )

    response = await llm.ainvoke(prompt)
    review = response.content
    if isinstance(review, str):
        review = strip_think_tags(review)

    if "COMPLETE" in review and "INCOMPLETE" not in review:
        state["is_complete"] = True
    else:
        # Extract refined query
        refined = review.replace("INCOMPLETE:", "").strip()
        if refined and len(refined) > 5:
            state["current_query"] = refined
            _emit_event(state, "reasoning", f"Refining search: {refined}")
        else:
            state["is_complete"] = True

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


def _extract_json(text: str) -> dict | None:
    """Extract a JSON object from LLM output, tolerating extra text or code fences."""
    text = text.strip()

    # Direct parse
    result = _try_parse_json(text)
    if result is not None:
        return result

    # Strip markdown code fences
    m = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        result = _try_parse_json(m.group(1).strip())
        if result is not None:
            return result

    # Find outermost { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        result = _try_parse_json(text[start : end + 1])
        if result is not None:
            return result

    # Final fallback: regex field extraction (handles LaTeX/JSON escape collisions)
    result = _regex_extract_fields(text)
    if result is not None:
        return result

    return None


async def final_response_node(state: ResearchState) -> ResearchState:
    """Synthesize a final answer from all research notes + conversation context."""
    llm = ChatOllama(model=AGENT_MODEL, temperature=0.3, num_predict=4096)

    notes_text = "\n".join(f"- {n}" for n in state["research_notes"]) if state["research_notes"] else "No specific research findings."
    history = "\n".join(f"{m['role']}: {m['content']}" for m in state["messages"][-6:])
    active_notes = state["current_note"][:2000] if state["current_note"] else "No active notes."

    active_title = state["active_note_title"] or "Untitled"
    mode_instruction = (
        EDIT_ALLOWED_INSTRUCTION.format(active_note_title=active_title)
        if state["allow_edits"]
        else CHAT_ONLY_INSTRUCTION
    )

    prompt = (FINAL_RESPONSE_WITH_ACTIONS_PROMPT
        .replace("{history}", history)
        .replace("{notes_text}", notes_text)
        .replace("{active_notes}", active_notes)
        .replace("{active_note_title}", active_title)
        .replace("{mode_instruction}", mode_instruction)
    )
    response = await llm.ainvoke(prompt)
    raw = response.content
    if isinstance(raw, str):
        raw = strip_think_tags(raw)

    if not raw.strip():
        if state["research_notes"]:
            notes_summary = "; ".join(state["research_notes"][:5])
            state["final_answer"] = f"Based on your notes, here's what I found: {notes_summary}"
        else:
            state["final_answer"] = "I couldn't find specific information about that. Could you rephrase?"
        return state

    data = _extract_json(raw)

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

    return state


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


async def run_research_agent(
    messages: list[dict[str, str]],
    current_note: str = "",
    allow_edits: bool = False,
    active_note_title: str = "",
    active_note_id: str | None = None,
    scope: list[str] | None = None,
) -> ResearchState:
    """
    Run the research agent to completion and return final state.

    For streaming, use `stream_research_agent` instead.
    """
    user_query = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_query = msg["content"]
            break

    initial_state: ResearchState = {
        "messages": messages,
        "current_note": current_note,
        "current_query": user_query,
        "research_notes": [],
        "retrieved_chunks": [],
        "loop_count": 0,
        "is_complete": False,
        "final_answer": "",
        "events": [],
        "allow_edits": allow_edits,
        "active_note_title": active_note_title,
        "active_note_id": active_note_id,
        "scope": scope,
    }

    result = await research_agent.ainvoke(initial_state)
    return result


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
    user_query = ""
    for msg in reversed(messages):
        if msg["role"] == "user":
            user_query = msg["content"]
            break

    initial_state: ResearchState = {
        "messages": messages,
        "current_note": current_note,
        "current_query": user_query,
        "research_notes": [],
        "retrieved_chunks": [],
        "loop_count": 0,
        "is_complete": False,
        "final_answer": "",
        "events": [],
        "allow_edits": allow_edits,
        "active_note_title": active_note_title,
        "active_note_id": active_note_id,
        "scope": scope,
    }

    last_event_count = 0

    async for state_update in research_agent.astream(initial_state):
        # Each state_update is a dict of {node_name: updated_state}
        for node_name, node_state in state_update.items():
            if node_name == "__end__":
                continue

            events = node_state.get("events", [])
            # Yield any new events since last check
            for event in events[last_event_count:]:
                yield event
            last_event_count = len(events)

            # If we have a final answer, yield it as text
            if node_state.get("final_answer"):
                yield {"type": "text", "content": node_state["final_answer"]}
