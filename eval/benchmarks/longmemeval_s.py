"""LongMemEval-S adapter: loader, history ingestion, exact-match judge.

Short numeric/boolean golds are exact-match scored here; long-prose golds and
abstention instances score 0 by this guard until the pinned LLM-judge follow-up
lands (aggregate reports will read artificially low — by design, never fabricate).
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

# Ingested turn content is capped so one haystack turn never becomes an oversized
# memory-create call; the official protocol applies the same chunk discipline.
_MAX_TURN_CHARS = 10_000

# Gold answers the non-LLM exact-match guard can score without a model.
_SHORT_ANSWER_TYPES = frozenset({"integer", "float", "boolean"})


@dataclass(frozen=True)
class BenchmarkTurn:
    """One haystack chat turn (``user``/``assistant``)."""

    role: str
    content: str
    has_answer: bool


@dataclass(frozen=True)
class BenchmarkSession:
    """One haystack chat session and its date."""

    session_id: str
    date: str
    turns: tuple[BenchmarkTurn, ...]


@dataclass(frozen=True)
class BenchmarkInstance:
    """One LongMemEval-S question with its haystack sessions and gold answer."""

    question_id: str
    question_type: str
    question: str
    answer: str
    question_date: str
    sessions: tuple[BenchmarkSession, ...]
    answer_session_ids: frozenset[str]


def _require(obj: dict, field: str, ctx: str) -> object:
    if field not in obj:
        raise ValueError(f"{ctx}: missing field {field!r}")
    return obj[field]


def _require_str(obj: dict, field: str, ctx: str, coerce_number: bool = False) -> str:
    value = _require(obj, field, ctx)
    if coerce_number and isinstance(value, (int, float)) and not isinstance(value, bool):
        # LongMemEval-S ships 32/500 numeric golds (e.g. 3 for "how many");
        # both the exact-match guard and the judge consume the string form.
        return str(value)
    if not isinstance(value, str):
        raise ValueError(f"{ctx}: field {field!r} must be a string, got {type(value).__name__}")
    return value


def _parse_turns(raw_turns: list, ctx: str) -> tuple[BenchmarkTurn, ...]:
    if not isinstance(raw_turns, list):
        raise ValueError(f"{ctx}: haystack session must be a list of turns")
    turns: list[BenchmarkTurn] = []
    for i, turn in enumerate(raw_turns):
        turn_ctx = f"{ctx} turn {i}"
        if not isinstance(turn, dict):
            raise ValueError(f"{turn_ctx}: turn must be an object")
        role = _require_str(turn, "role", turn_ctx)
        if role not in ("user", "assistant"):
            raise ValueError(f"{turn_ctx}: role must be 'user' or 'assistant', got {role!r}")
        content = _require_str(turn, "content", turn_ctx)
        turns.append(BenchmarkTurn(role=role, content=content, has_answer=bool(turn.get("has_answer", False))))
    return tuple(turns)


def load_instances(path: Path) -> list[BenchmarkInstance]:
    """Load a LongMemEval-S fixture/dataset file into typed instances.

    Validates the official schema (required fields, parallel ``haystack_*``
    arrays, ``user``/``assistant`` roles) and raises ``ValueError`` on any
    malformed record — never returns a half-loaded list.
    """
    records = json.loads(Path(path).read_text())
    if not isinstance(records, list):
        raise ValueError(f"{path}: top-level JSON must be an array of instances, got {type(records).__name__}")

    instances: list[BenchmarkInstance] = []
    for idx, record in enumerate(records):
        ctx = f"{path} instance {idx}"
        if not isinstance(record, dict):
            raise ValueError(f"{ctx}: instance must be an object")

        session_ids = _require(record, "haystack_session_ids", ctx)
        dates = _require(record, "haystack_dates", ctx)
        sessions_raw = _require(record, "haystack_sessions", ctx)
        if not (isinstance(session_ids, list) and isinstance(dates, list) and isinstance(sessions_raw, list)):
            raise ValueError(f"{ctx}: haystack_session_ids/haystack_dates/haystack_sessions must all be lists")
        if not (len(session_ids) == len(dates) == len(sessions_raw)):
            raise ValueError(
                f"{ctx}: parallel haystack arrays must have equal length, got "
                f"{len(session_ids)}/{len(dates)}/{len(sessions_raw)}"
            )

        answer_session_ids = _require(record, "answer_session_ids", ctx)
        if not isinstance(answer_session_ids, list):
            raise ValueError(f"{ctx}: answer_session_ids must be a list")
        unknown = set(answer_session_ids) - set(session_ids)
        if unknown:
            raise ValueError(f"{ctx}: answer_session_ids not in haystack_session_ids: {sorted(unknown)}")

        sessions = tuple(
            BenchmarkSession(
                session_id=session_ids[i],
                date=dates[i],
                turns=_parse_turns(sessions_raw[i], f"{ctx} haystack session {session_ids[i]!r}"),
            )
            for i in range(len(session_ids))
        )

        instances.append(
            BenchmarkInstance(
                question_id=_require_str(record, "question_id", ctx),
                question_type=_require_str(record, "question_type", ctx),
                question=_require_str(record, "question", ctx),
                answer=_require_str(record, "answer", ctx, coerce_number=True),
                question_date=_require_str(record, "question_date", ctx),
                sessions=sessions,
                answer_session_ids=frozenset(answer_session_ids),
            )
        )
    return instances


def is_abstention(instance: BenchmarkInstance) -> bool:
    """True when the gold answer is LongMemEval's abstention variant."""
    return instance.question_id.endswith("_abs")


async def ingest_history(
    session: BenchmarkSession,
    *,
    create_memory: Callable[[str, str], Awaitable[None]],
) -> None:
    """Ingest one session as one memory per turn via the injected callable.

    Each turn becomes a single ``create_memory(content, source)`` call:
    content carries a ``[role]`` prefix plus the session date as the first
    line, capped at ``10_000`` characters. ``source`` carries the session id
    so live runs can trace memories back to haystack sessions.
    """
    for turn in session.turns:
        body = turn.content[:_MAX_TURN_CHARS]
        content = f"[{turn.role}] {session.date}\n{body}"
        await create_memory(content, session.session_id)


async def run_query(instance: BenchmarkInstance, *, recall: Callable[[str], Awaitable[str]]) -> str:
    """Ask the injected recall callable one question and return its answer text."""
    return await recall(instance.question)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def judge_answer(question: str, answer: str, response: str) -> bool:
    """Conservative non-LLM guard, NOT the official judge — official LongMemEval scoring is judge-based for ALL question types (pinned follow-up).

    Case-insensitive, whitespace-normalized word-boundary match of the gold
    answer in the response, restricted to short numeric/boolean gold answers
    (so ``"3"`` never matches inside ``"35"``). Everything else needs the LLM
    judge (protocol follow-up) and scores False.
    """
    del question  # question is not used by the exact-match guard; kept for LLM-judge parity
    if _infer_answer_type(answer) in _SHORT_ANSWER_TYPES:
        gold = _normalize(answer)
        return re.search(rf"(?<!\w){re.escape(gold)}(?!\w)", _normalize(response)) is not None
    return False


def _infer_answer_type(answer: str) -> str:
    """Best-effort short-answer type inference for the non-LLM guard.

    Integer/float golds are detected by successful numeric parsing;
    booleans by the official yes/no variants. Anything else needs the LLM
    judge and is reported as ``"text"``.
    """
    if not answer:
        return "text"
    stripped = answer.strip().lower()
    if stripped in ("yes", "no", "true", "false"):
        return "boolean"
    try:
        int(stripped)
    except ValueError:
        pass
    else:
        return "integer"
    try:
        float(stripped)
    except ValueError:
        return "text"
    return "float"
