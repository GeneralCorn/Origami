"""Append-only ledger of every model call the backend makes.

PRIVACY, non-negotiable: this ledger records no prompt text and no response
text, ever. prompt_chars is the only content-derived field and it is a size
proxy. A usage ledger that quietly accumulated every question the user asked
would violate the premise of a local knowledge base, so do not add a prompt
preview, a response snippet, a query, or a filename to CallRecord.

One file per month under DATA_DIR/usage. Bucketing by filename bounds file
size with no rotation logic, following the precedent in services/digest.py.
"""

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import USAGE_DIR

logger = logging.getLogger(__name__)

REQUESTS_DIR = USAGE_DIR / "requests"


@dataclass(frozen=True, slots=True)
class CallRecord:
    """One model call. Written once, never updated."""

    ts: str
    purpose: str
    route: str
    origin: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    billable_input_tokens: int
    elapsed_s: float
    prompt_chars: int
    cost_usd: float
    priced: bool
    turn_id: str
    loop: int
    stub: bool


@dataclass(frozen=True, slots=True)
class JsonStrategyRecord:
    """Which _extract_json strategy recovered a final_response payload.

    Kept in its own file rather than as a CallRecord field because the
    strategy is only known after the response has been parsed, by which
    point the call record has already been appended, and rewriting a line
    in an append-only ledger is worse than a second append.
    """

    ts: str
    turn_id: str
    model: str
    strategy: str


def _stamp(when: datetime | None = None) -> str:
    return (when or datetime.now(timezone.utc)).strftime("%Y-%m")


def ledger_path(when: datetime | None = None) -> Path:
    return USAGE_DIR / f"usage-{_stamp(when)}.jsonl"


def json_strategy_path(when: datetime | None = None) -> Path:
    return USAGE_DIR / f"json-strategy-{_stamp(when)}.jsonl"


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(line)


async def _append(path: Path, payload: dict[str, Any], what: str) -> None:
    """Append one JSON line off the event loop.

    A ledger write must never fail a turn: losing a metric is acceptable,
    losing the user's answer is not. The failure is logged rather than
    swallowed so a permanently unwritable data dir is diagnosable.
    """
    try:
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _append_line, path, line)
    except Exception:
        logger.error("failed to append %s to %s", what, path, exc_info=True)


async def record(rec: CallRecord) -> None:
    await _append(ledger_path(), asdict(rec), f"usage record (purpose={rec.purpose})")


async def record_json_strategy(turn_id: str, model: str, strategy: str) -> None:
    rec = JsonStrategyRecord(
        ts=datetime.now(timezone.utc).isoformat(),
        turn_id=turn_id,
        model=model,
        strategy=strategy,
    )
    await _append(json_strategy_path(), asdict(rec), "json strategy record")


async def dump_request(turn_id: str, seq: int, purpose: str, payload: dict[str, Any]) -> None:
    """Write the would-be API request under stub mode.

    This is the only place request payloads touch disk, and it is reachable
    only when ORIGAMI_MODEL_STUB is set — i.e. in tests and in a keyless
    development run, never on a path that serves a real user.
    """
    try:
        REQUESTS_DIR.mkdir(parents=True, exist_ok=True)
        path = REQUESTS_DIR / f"{turn_id}-{seq}-{purpose}.json"
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, path.write_text, json.dumps(payload, indent=2, ensure_ascii=False)
        )
    except Exception:
        logger.error("failed to dump stub request for purpose=%s", purpose, exc_info=True)


@dataclass
class _Totals:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    elapsed_s: float = 0.0

    def add(self, row: dict[str, Any]) -> None:
        self.calls += 1
        self.input_tokens += int(row.get("input_tokens", 0))
        self.output_tokens += int(row.get("output_tokens", 0))
        self.cache_read_tokens += int(row.get("cache_read_tokens", 0))
        self.cache_creation_tokens += int(row.get("cache_creation_tokens", 0))
        self.cost_usd += float(row.get("cost_usd", 0.0))
        self.elapsed_s += float(row.get("elapsed_s", 0.0))

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["cost_usd"] = round(self.cost_usd, 6)
        out["elapsed_s"] = round(self.elapsed_s, 3)
        return out


@dataclass
class _Group:
    buckets: dict[str, _Totals] = field(default_factory=dict)

    def add(self, key: str, row: dict[str, Any]) -> None:
        self.buckets.setdefault(key or "-", _Totals()).add(row)

    def as_dict(self) -> dict[str, Any]:
        return {k: v.as_dict() for k, v in sorted(self.buckets.items())}


def _iter_lines(path: Path):
    """Yield parsed rows, skipping any line a crash left half-written."""
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                logger.warning("skipping malformed ledger line in %s", path.name)


def month_to_date(when: datetime | None = None) -> dict[str, Any]:
    """Aggregate the current month's ledger, streaming line by line."""
    total = _Totals()
    by_purpose = _Group()
    by_model = _Group()
    by_route = _Group()
    by_origin = _Group()
    unpriced_calls = 0
    stub_calls = 0

    for row in _iter_lines(ledger_path(when)):
        total.add(row)
        by_purpose.add(str(row.get("purpose", "")), row)
        by_model.add(str(row.get("model", "")), row)
        by_route.add(str(row.get("route", "")), row)
        by_origin.add(str(row.get("origin", "")), row)
        if not row.get("priced", False):
            unpriced_calls += 1
        if row.get("stub", False):
            stub_calls += 1

    strategies: dict[str, int] = {}
    for row in _iter_lines(json_strategy_path(when)):
        key = str(row.get("strategy", "unknown"))
        strategies[key] = strategies.get(key, 0) + 1

    return {
        "month": _stamp(when),
        "total": total.as_dict(),
        "unpriced_calls": unpriced_calls,
        "stub_calls": stub_calls,
        "by_purpose": by_purpose.as_dict(),
        "by_model": by_model.as_dict(),
        "by_route": by_route.as_dict(),
        "by_origin": by_origin.as_dict(),
        "json_strategies": dict(sorted(strategies.items())),
    }
