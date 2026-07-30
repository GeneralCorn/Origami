"""The single chokepoint every model call in this backend routes through.

ChatAnthropic is constructed here and nowhere else. That is what makes
instrumentation, model routing, the per-turn call ceiling, and the refusal
to send session state from background work enforceable rather than
advisory: a new call site cannot opt out without adding a second
construction, which tests/test_budget_enforcement.py fails on.
"""

import logging
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

import prompts
from config import (
    ANTHROPIC_API_KEY,
    CHEAP_FINAL,
    HAIKU_MODEL,
    MAX_LOOPS_CLAMP,
    MODEL_STUB,
    SONNET_MODEL,
)
from services import usage
from services.pricing import cost_usd
from services.text_utils import strip_think_tags

logger = logging.getLogger(__name__)


class Purpose(StrEnum):
    """The closed set of reasons this backend calls a model."""

    CLASSIFY = "classify"
    FAST_FACT = "fast_fact"
    ANALYZE = "analyze"
    REVIEW = "review"
    FINAL_RESPONSE = "final_response"
    CONTEXTUALIZE = "contextualize"


class ContextBudgetError(RuntimeError):
    """Raised when non-interactive work tries to send the session's state."""


class CallBudgetExceeded(RuntimeError):
    """Raised when a turn tries to make more model calls than its route allows."""


# Placeholders that carry the interactive session's state: the conversation,
# the user's notes, their query, or corpus text retrieved on their behalf.
# A prompt built from any of these may only be sent by an interactive turn.
CONTEXT_FIELDS = frozenset({
    "history", "query", "current_query", "original_question",
    "notes_text", "current_notes", "active_notes",
    "note_preview", "note_section", "chunks_text", "active_note_title",
})

# Placeholders a background job may send. whole_document and chunk_content
# are user bytes, but they are the ingest job's own explicit payload rather
# than state borrowed from a live session, and that is the line Lever 2
# draws: background work may process what it was handed, and may not reach
# into the conversation.
CONTEXT_FREE_FIELDS = frozenset({
    "whole_document", "chunk_content", "mode_instruction", "action_protocol",
})

# Case-insensitive on purpose. A lowercase-only pattern let {History} slip
# past both the classification check and the session-state derivation, which
# turned the choice of capital letter into a way out of Lever 2.
_PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")

# The closed set of texts this backend may send. Membership is by value, so
# only a module-level constant in prompts/ qualifies; a string a caller
# built at runtime does not, however it was spelled. Without this, Lever 2
# was enforced by placeholder name alone and an f-string that pasted the
# conversation straight into the template carried no fields at all, so it
# derived carries_session_state=False and a background permit sent it.
_REGISTERED_TEMPLATES: frozenset[str] = frozenset(
    value for name in prompts.__all__
    if isinstance(value := getattr(prompts, name), str)
)


@dataclass(frozen=True, slots=True)
class Prompt:
    """A rendered prompt plus a derived statement of what it carries."""

    text: str
    fields: tuple[str, ...]
    carries_session_state: bool
    cache_prefix: str | None = None

    @classmethod
    def render(
        cls,
        template: str,
        fields: dict[str, str],
        *,
        mode: str = "format",
        cache_after: str | None = None,
    ) -> "Prompt":
        """Render a template, deriving rather than accepting what it carries.

        carries_session_state comes from which placeholders were actually
        filled, so a caller cannot assert a background-safe prompt into
        existence; it would have to rename its placeholders out of the
        session vocabulary, which the enforcement tests catch.

        template must be one of the constants in prompts/. That is what
        makes the derivation meaningful: a caller who interpolates the
        conversation into the template itself produces a prompt with no
        fields to derive from, and the gate would wave it through.

        mode="replace" exists because FINAL_RESPONSE_WITH_ACTIONS_PROMPT
        contains literal JSON braces and cannot go through str.format.

        cache_after names the placeholder to end a cacheable prefix at. The
        template is split after that placeholder and rendered in two halves,
        so cache_prefix + text is byte-identical to the whole rendered
        prompt while the prefix stays constant across calls.
        """
        used = tuple(sorted(set(_PLACEHOLDER.findall(template)) & set(fields)))
        unclassified = [
            f for f in used
            if f not in CONTEXT_FIELDS and f not in CONTEXT_FREE_FIELDS
        ]
        if unclassified:
            raise ValueError(
                f"prompt fields {unclassified} are in neither CONTEXT_FIELDS nor "
                "CONTEXT_FREE_FIELDS — classify them so Budget can gate on them"
            )
        if template not in _REGISTERED_TEMPLATES:
            raise ValueError(
                "template is not one of the constants exported by prompts/. "
                "session state pasted into a template carries no fields, so "
                "Budget cannot gate on it. Add the template to prompts/ and "
                "pass the variable parts as classified fields."
            )

        head, tail = _split_template(template, cache_after)
        return cls(
            text=_substitute(tail, fields, mode),
            fields=used,
            carries_session_state=any(f in CONTEXT_FIELDS for f in used),
            cache_prefix=None if head is None else _substitute(head, fields, mode),
        )

    @property
    def char_count(self) -> int:
        return len(self.text) + len(self.cache_prefix or "")

    def to_messages(self) -> list[BaseMessage]:
        """Render to messages, marking the cache prefix when there is one.

        The breakpoint is set per content block rather than through the
        cache_control invoke kwarg, because that kwarg attaches to the last
        eligible block and the reusable prefix is the first.
        """
        if self.cache_prefix is None:
            return [HumanMessage(content=self.text)]
        return [HumanMessage(content=[
            {
                "type": "text",
                "text": self.cache_prefix,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": self.text},
        ])]


def _split_template(template: str, cache_after: str | None) -> tuple[str | None, str]:
    if cache_after is None:
        return None, template
    marker = "{" + cache_after + "}"
    idx = template.find(marker)
    if idx == -1:
        raise ValueError(f"cache_after={cache_after!r} is not a placeholder in the template")
    cut = idx + len(marker)
    return template[:cut], template[cut:]


def _substitute(template: str, fields: dict[str, str], mode: str) -> str:
    if mode == "format":
        return template.format(**fields)
    if mode == "replace":
        out = template
        for key, value in fields.items():
            out = out.replace("{" + key + "}", value)
        return out
    raise ValueError(f"unknown render mode {mode!r}")


@dataclass(frozen=True, slots=True)
class ModelSpec:
    model: str
    max_tokens: int
    temperature: float


_SPECS: dict[Purpose, ModelSpec] = {
    Purpose.CLASSIFY: ModelSpec(HAIKU_MODEL, 10, 0.0),
    Purpose.FAST_FACT: ModelSpec(HAIKU_MODEL, 1024, 0.3),
    # Never route analyze to Sonnet. It is the most repeated call in the
    # pipeline — up to three per turn, each carrying ~1.5k tokens of chunks
    # plus every accumulated note — so escalating it multiplies the largest
    # input term by 5x to improve the single synthesis it feeds. Reading
    # "route by difficulty" as "use the big model on hard queries" would do
    # exactly that, and it is the wrong move here.
    Purpose.ANALYZE: ModelSpec(HAIKU_MODEL, 2048, 0.0),
    # The prompt constrains the answer to the literal word COMPLETE or one
    # refined query. 256 bounds the worst case; output is billed on actual
    # tokens, so this is not itself a saving.
    Purpose.REVIEW: ModelSpec(HAIKU_MODEL, 256, 0.0),
    Purpose.CONTEXTUALIZE: ModelSpec(HAIKU_MODEL, 100, 0.0),
}


def resolve_model(purpose: Purpose, route: str, *, has_notes: bool = True) -> ModelSpec:
    """Pick the model and output ceiling for one call. Pure function.

    Every purpose but the final synthesis is locked to Haiku. The final
    synthesis never sees retrieved chunks — only Haiku's distilled notes,
    the last six messages, and the active note — so Sonnet earns its price
    there only when there is cross-source material to compose from:

    - no notes: nothing to synthesize. This fires whenever retrieval came
      back empty, which an empty or new knowledge base hits constantly, and
      today it pays for Sonnet at 4096 output tokens to say it found
      nothing. Downgraded by default, with no quality bet at all.
    - deep_research with notes: notes span up to three retrieval passes
      with query refinement between them. This is the case the product is
      for, and it is a hard Sonnet floor.
    - normal_rag with notes: one analyze pass over five chunks. Haiku is
      structurally defensible and this is the modal turn, but the node must
      emit a single valid JSON object containing LaTeX and _extract_json
      already needs four recovery strategies. Downgrading the main answer
      path on a bet nobody can measure is the worst available trade, so it
      sits behind ORIGAMI_CHEAP_FINAL until the recorded json_strategy
      distribution shows Haiku is no worse.
    """
    if purpose is Purpose.FINAL_RESPONSE:
        cheap = not has_notes or (route != "deep_research" and CHEAP_FINAL)
        return ModelSpec(HAIKU_MODEL if cheap else SONNET_MODEL, 4096, 0.3)
    return _SPECS[purpose]


def max_calls_for(route: str, max_loops: int) -> int:
    """Upper bound on model calls for one interactive turn.

    fast_fact is the classifier plus one answer. Every other route is the
    classifier, one analyze per loop, one review per loop after the first
    (the last pass needs no continue-decision), and one final synthesis.

    The review term is floored at zero. Written as 2 * max_loops + 1 it
    silently subtracted a call at max_loops=0, returning 1, one below the
    two calls (classify + final_response) every graph route makes before
    max_loops is even consulted, because it is only read in review_node
    and review_node runs after retrieve -> analyze. config._parse_loops now
    refuses 0 for the graph routes, so this is the second of two floors
    rather than the only one.
    """
    if route == "fast_fact":
        return 2
    return 1 + max_loops + max(0, max_loops - 1) + 1


_INTERACTIVE_ORIGIN = "interactive"


@dataclass(slots=True)
class Budget:
    """A per-turn permit. Passing one is how a caller states its origin."""

    origin: str
    route: str
    max_calls: int
    turn_id: str
    calls_made: int = 0

    @property
    def may_send_context(self) -> bool:
        """Derived from origin, never stored.

        As a settable field this was one assignment away from defeating
        Lever 2: Budget is mutable because authorize and adopt_route write
        to it, so `b = Budget.background(...); b.may_send_context = True`
        turned a background permit into an interactive one. Deriving it
        means the only way to obtain the permission is to claim the
        interactive origin, which tests/test_budget_enforcement.py pins to
        a single call site.
        """
        return self.origin == _INTERACTIVE_ORIGIN

    @classmethod
    def interactive(cls, route: str = "", max_loops: int = MAX_LOOPS_CLAMP) -> "Budget":
        """A permit for a live user turn. The only kind that may send context.

        Minted before the route is known, because the classifier's own
        tokens belong to the turn they classify, so it opens on the widest
        possible ceiling and is narrowed by adopt_route once the route is
        decided. Only the classifier call happens in between.
        """
        return cls(
            origin=_INTERACTIVE_ORIGIN,
            route=route,
            max_calls=max_calls_for(route, max_loops),
            turn_id=str(uuid.uuid4()),
        )

    @classmethod
    def background(cls, origin: str, max_calls: int) -> "Budget":
        if origin == _INTERACTIVE_ORIGIN:
            raise ValueError(
                "background work may not claim the interactive origin, which "
                "is the only origin permitted to send session state"
            )
        return cls(
            origin=origin,
            route="",
            max_calls=max(1, max_calls),
            turn_id=str(uuid.uuid4()),
        )

    def adopt_route(self, route: str, max_loops: int) -> None:
        self.route = route
        self.max_calls = max_calls_for(route, max_loops)

    def authorize(self, purpose: Purpose, prompt: Prompt) -> None:
        if prompt.carries_session_state and not self.may_send_context:
            raise ContextBudgetError(
                f"origin={self.origin} may not send session state "
                f"(purpose={purpose.value}, fields={list(prompt.fields)})"
            )
        if self.calls_made >= self.max_calls:
            raise CallBudgetExceeded(
                f"turn {self.turn_id} exceeded its {self.max_calls}-call ceiling "
                f"at purpose={purpose.value} (route={self.route or '-'})"
            )
        self.calls_made += 1


@dataclass(frozen=True, slots=True)
class ModelResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    elapsed_s: float
    cost_usd: float
    priced: bool


_STUB_TEXT: dict[Purpose, str] = {
    Purpose.CLASSIFY: "NORMAL_RAG",
    Purpose.FAST_FACT: "Stubbed fast-fact answer.",
    Purpose.ANALYZE: (
        "- Stubbed finding one drawn from the retrieved excerpts.\n"
        "- Stubbed finding two drawn from the retrieved excerpts."
    ),
    # Deliberately never COMPLETE: a stubbed review that keeps asking for
    # another pass is what makes the loop ceiling the thing under test.
    Purpose.REVIEW: "INCOMPLETE: stubbed refined query",
    Purpose.FINAL_RESPONSE: '{"action": "chat", "message": "Stubbed final answer."}',
    Purpose.CONTEXTUALIZE: "Stubbed context blurb situating this chunk.",
}


def _stub_response(purpose: Purpose, prompt: Prompt) -> AIMessage:
    """A canned response shaped like the real one, with synthetic counts.

    Cache token counts stay zero: the stub cannot know whether Anthropic
    would have hit the cache, and reporting a hit it did not measure would
    make the ledger lie. The cache block structure is proven instead by
    inspecting the dumped request.
    """
    text = _STUB_TEXT[purpose]
    msg = AIMessage(content=text, response_metadata={"model_name": "stub"})
    msg.usage_metadata = {
        "input_tokens": max(1, prompt.char_count // 4),
        "output_tokens": max(1, len(text) // 4),
        "total_tokens": max(1, prompt.char_count // 4) + max(1, len(text) // 4),
        "input_token_details": {},
    }
    return msg


def _request_payload(purpose: Purpose, spec: ModelSpec, prompt: Prompt) -> dict[str, Any]:
    return {
        "purpose": purpose.value,
        "model": spec.model,
        "max_tokens": spec.max_tokens,
        "temperature": spec.temperature,
        "messages": [{"role": "user", "content": m.content} for m in prompt.to_messages()],
    }


def _response_text(content: Any) -> str:
    """Flatten response content to text.

    Anthropic returns a block list rather than a string whenever citations
    or thinking blocks are present, and every caller here wants prose.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content or "")


def _to_result(response: Any, spec: ModelSpec, elapsed: float, stub: bool) -> ModelResult:
    meta = getattr(response, "usage_metadata", None) or {}
    # input_token_details omits its keys when the value is None.
    details = meta.get("input_token_details") or {}
    cache_read = details.get("cache_read", 0) or 0
    cache_creation = details.get("cache_creation", 0) or 0
    input_tokens = meta.get("input_tokens", 0) or 0
    output_tokens = meta.get("output_tokens", 0) or 0

    # Keyed on what the API reported, not on the configured constant: both
    # model ids are env-overridable and SONNET_MODEL defaults to an undated
    # alias while the API answers with a dated id.
    reported = (getattr(response, "response_metadata", None) or {}).get("model_name")
    model = spec.model if stub else (reported or spec.model)

    if stub:
        # The stub estimates its token counts from character length, so
        # pricing them at the real per-token rate for the model the router
        # picked invents dollars. It reported priced=True under the real
        # model id, which made a keyless development run indistinguishable
        # from real spend in every month_to_date aggregate. The routed model
        # id is still recorded, because which model a route picks is a claim
        # the stub exists to verify. Only the money is withheld.
        cost, priced = 0.0, False
    elif not meta:
        # A response with no usage block would otherwise resolve a real rate
        # against zeroed counts and record a priced $0.00 call, reporting the
        # pipeline as free. priced=False routes it to unpriced_calls instead.
        logger.error(
            "no usage metadata on a %s response from %s, recording the call as unpriced",
            spec.model, type(response).__name__,
        )
        cost, priced = 0.0, False
    else:
        cost, priced = cost_usd(model, input_tokens, output_tokens, cache_read, cache_creation)
    return ModelResult(
        text=strip_think_tags(_response_text(getattr(response, "content", ""))),
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_creation_tokens=cache_creation,
        elapsed_s=elapsed,
        cost_usd=cost,
        priced=priced,
    )


async def _record_call(
    purpose: Purpose,
    budget: Budget,
    prompt: Prompt,
    result: ModelResult,
    loop: int,
    *,
    failed: bool,
) -> None:
    await usage.record(usage.CallRecord(
        ts=datetime.now(timezone.utc).isoformat(),
        purpose=purpose.value,
        route=budget.route,
        origin=budget.origin,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cache_read_tokens=result.cache_read_tokens,
        cache_creation_tokens=result.cache_creation_tokens,
        billable_input_tokens=max(
            0,
            result.input_tokens - result.cache_read_tokens - result.cache_creation_tokens,
        ),
        elapsed_s=round(result.elapsed_s, 4),
        prompt_chars=prompt.char_count,
        cost_usd=result.cost_usd,
        priced=result.priced,
        turn_id=budget.turn_id,
        loop=loop,
        stub=MODEL_STUB,
        failed=failed,
    ))


def _failed_result(spec: ModelSpec, elapsed: float) -> ModelResult:
    """The row for a call that was authorized and then raised.

    Zero tokens and priced=False, because nothing was measured: the provider
    may have billed the input and there is no way to know how much.
    """
    return ModelResult(
        text="",
        model=spec.model,
        input_tokens=0,
        output_tokens=0,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        elapsed_s=elapsed,
        cost_usd=0.0,
        priced=False,
    )


async def complete(
    purpose: Purpose,
    prompt: Prompt,
    budget: Budget,
    *,
    loop: int = 0,
    has_notes: bool = True,
) -> ModelResult:
    """Authorize, route, invoke, time, and record one model call.

    budget is required rather than defaulted: omitting it is a TypeError,
    which is louder and safer than a permissive default.
    """
    budget.authorize(purpose, prompt)
    spec = resolve_model(purpose, budget.route, has_notes=has_notes)
    seq = budget.calls_made

    t0 = time.perf_counter()
    try:
        if MODEL_STUB:
            await usage.dump_request(
                budget.turn_id, seq, purpose.value, _request_payload(purpose, spec, prompt)
            )
            response: Any = _stub_response(purpose, prompt)
        else:
            if not ANTHROPIC_API_KEY:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Set it, or set ORIGAMI_MODEL_STUB=1 "
                    "to run the pipeline against local stubs."
                )
            llm = ChatAnthropic(
                model=spec.model,
                api_key=ANTHROPIC_API_KEY,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
            )
            response = await llm.ainvoke(prompt.to_messages())
    except Exception as exc:
        # authorize() already spent the budget slot, so returning here
        # without a row let the turn's call count exceed its ledger rows and
        # made ingest's [COST] line understate a document by exactly its
        # failed chunks, the chunks its own comment calls billed.
        elapsed = time.perf_counter() - t0
        logger.error(
            "[COST] %s route=%s model=%s FAILED after %.3fs, recorded unpriced: %s",
            purpose.value, budget.route or "-", spec.model, elapsed, exc,
        )
        await _record_call(
            purpose, budget, prompt, _failed_result(spec, elapsed), loop, failed=True
        )
        raise
    elapsed = time.perf_counter() - t0

    result = _to_result(response, spec, elapsed, MODEL_STUB)
    await _record_call(purpose, budget, prompt, result, loop, failed=False)
    logger.info(
        "[COST] %s route=%s model=%s %d in (%d cached) / %d out — $%.6f in %.3fs",
        purpose.value, budget.route or "-", result.model, result.input_tokens,
        result.cache_read_tokens, result.output_tokens, result.cost_usd, elapsed,
    )
    return result
