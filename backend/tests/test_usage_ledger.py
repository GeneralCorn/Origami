import json
from datetime import datetime, timezone

from services import usage
from services.usage import CallRecord


def _rec(**over) -> CallRecord:
    base = dict(
        ts=datetime.now(timezone.utc).isoformat(),
        purpose="analyze",
        route="normal_rag",
        origin="interactive",
        model="claude-haiku-4-5-20251001",
        input_tokens=1500,
        output_tokens=200,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        billable_input_tokens=1500,
        elapsed_s=1.25,
        prompt_chars=6000,
        cost_usd=0.0025,
        priced=True,
        turn_id="turn-1",
        loop=0,
        stub=False,
        failed=False,
    )
    base.update(over)
    return CallRecord(**base)


async def test_append_and_aggregate():
    await usage.record(_rec())
    await usage.record(_rec(purpose="final_response", model="claude-sonnet-4-6",
                            input_tokens=800, output_tokens=900, cost_usd=0.0159))

    mtd = usage.month_to_date()

    assert mtd["total"]["calls"] == 2
    assert mtd["total"]["input_tokens"] == 2300
    assert mtd["total"]["output_tokens"] == 1100
    assert set(mtd["by_purpose"]) == {"analyze", "final_response"}
    assert set(mtd["by_model"]) == {"claude-haiku-4-5-20251001", "claude-sonnet-4-6"}
    assert mtd["by_route"]["normal_rag"]["calls"] == 2
    assert mtd["stub_calls"] == 0
    assert mtd["failed_calls"] == 0


async def test_monthly_bucketing_is_by_filename():
    await usage.record(_rec())
    assert usage.ledger_path().name == f"usage-{datetime.now(timezone.utc):%Y-%m}.jsonl"

    other = datetime(2001, 3, 4, tzinfo=timezone.utc)
    assert usage.month_to_date(other)["total"]["calls"] == 0


async def test_unpriced_calls_are_reported_not_hidden():
    await usage.record(_rec(priced=False, cost_usd=0.0, model="qwen2.5-vl:7b"))
    await usage.record(_rec())

    mtd = usage.month_to_date()
    assert mtd["unpriced_calls"] == 1
    assert mtd["total"]["calls"] == 2


async def test_unpriced_calls_means_unknown_model_not_stubbed_run():
    """Stub rows are unpriced by construction, and would swamp the counter.

    unpriced_calls exists so a stale price table shows as a gap. Folding in
    every call of a keyless development run would make that gap unreadable,
    so stubs are counted by stub_calls and excluded here.
    """
    await usage.record(_rec(stub=True, priced=False, cost_usd=0.0))
    await usage.record(_rec(priced=False, cost_usd=0.0, model="qwen2.5-vl:7b"))

    mtd = usage.month_to_date()
    assert mtd["unpriced_calls"] == 1
    assert mtd["stub_calls"] == 1


async def test_stub_rows_are_subtractable_from_a_blended_month():
    """A keyless run and a real key write to the same monthly file.

    Stub token counts are estimated from character length, so the reader
    needs the stub subtotal to recover the real one rather than a boolean
    saying some of the number is fictional.
    """
    await usage.record(_rec(stub=True, priced=False, cost_usd=0.0, input_tokens=400,
                            output_tokens=10, billable_input_tokens=400))
    await usage.record(_rec())

    mtd = usage.month_to_date()
    assert mtd["total"]["input_tokens"] == 1900
    assert mtd["stub"]["input_tokens"] == 400
    assert mtd["stub"]["cost_usd"] == 0.0
    assert mtd["total"]["input_tokens"] - mtd["stub"]["input_tokens"] == 1500
    assert mtd["total"]["cost_usd"] == 0.0025


async def test_failed_calls_are_counted_separately():
    """A call that raised is spend that bought nothing, not an unknown model."""
    await usage.record(_rec(failed=True, priced=False, cost_usd=0.0,
                            input_tokens=0, output_tokens=0, billable_input_tokens=0))
    await usage.record(_rec())

    mtd = usage.month_to_date()
    assert mtd["failed_calls"] == 1
    assert mtd["total"]["calls"] == 2
    assert mtd["unpriced_calls"] == 1


async def test_ledger_holds_no_prompt_or_response_text():
    """The privacy rule, enforced rather than documented.

    Nothing in a record may carry content. The field set is asserted whole
    so adding a prompt preview fails here before it ships.
    """
    await usage.record(_rec())
    rows = [json.loads(line) for line in usage.ledger_path().read_text().splitlines()]

    assert set(rows[0]) == {
        "ts", "purpose", "route", "origin", "model", "input_tokens",
        "output_tokens", "cache_read_tokens", "cache_creation_tokens",
        "billable_input_tokens", "elapsed_s", "prompt_chars", "cost_usd",
        "priced", "turn_id", "loop", "stub", "failed",
    }


async def test_malformed_line_does_not_break_aggregation():
    await usage.record(_rec())
    with open(usage.ledger_path(), "a") as f:
        f.write("{ truncated by a crash\n")
    await usage.record(_rec())

    assert usage.month_to_date()["total"]["calls"] == 2


async def test_json_strategy_distribution():
    await usage.record_json_strategy("turn-1", "claude-sonnet-4-6", "direct")
    await usage.record_json_strategy("turn-2", "claude-sonnet-4-6", "regex")
    await usage.record_json_strategy("turn-3", "claude-sonnet-4-6", "direct")

    assert usage.month_to_date()["json_strategies"] == {"direct": 2, "regex": 1}
