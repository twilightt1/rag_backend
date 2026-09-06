"""Regression: real LongMemEval-S ships numeric golds — loader coerces."""
from __future__ import annotations

from eval.benchmarks.longmemeval_s import _require_str


def test_require_str_coerces_numeric_answers():
    assert _require_str({"answer": 3}, "answer", "ctx", coerce_number=True) == "3"
    assert _require_str({"answer": 2.0}, "answer", "ctx", coerce_number=True) == "2.0"


def test_require_str_still_strict_without_coercion():
    import pytest

    with pytest.raises(ValueError, match="must be a string"):
        _require_str({"answer": 3}, "answer", "ctx")
    # bools are never coerced (True is not "True" in the dataset's semantics)
    with pytest.raises(ValueError, match="must be a string"):
        _require_str({"answer": True}, "answer", "ctx", coerce_number=True)


def test_require_str_accepts_strings():
    assert _require_str({"answer": "Runkeeper"}, "answer", "ctx") == "Runkeeper"


def test_vector_store_collection_wrapped_in_local_mode(monkeypatch):
    """Regression from the real system run: local (lite) Chroma returns a
    sync Collection whose count()/query() are plain ints/lists — call sites
    `await` them. The wrapper must be applied to the COLLECTION too, not
    just the client, or every search fails silently (recalled=0)."""
    import asyncio
    import inspect
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        # Patch settings, not just env: app.config.settings is a module
        # singleton built at first import (likely BEFORE this test set any
        # env), and vector_store reads settings.* — env changes alone are
        # invisible in a combined test run.
        from app.config import settings
        from app.retrieval.memory import vector_store

        monkeypatch.setattr(settings, "CHROMA_MODE", "local")
        monkeypatch.setattr(settings, "CHROMA_LOCAL_PATH", str(Path(tmp) / "chroma"))

        # Reset cached clients — earlier tests may have built one against
        # a different (read-only) path; the singleton would ignore ours.
        vector_store._sync_client = None
        vector_store._async_client = None

        async def _check():
            collection = await vector_store._get_collection()
            return (
                inspect.iscoroutinefunction(collection.count),
                inspect.iscoroutinefunction(collection.query),
            )

        count_async, query_async = asyncio.run(_check())
    assert count_async and query_async, (
        "local-mode collection must expose awaitable count/query — "
        "raw sync methods silently break recall"
    )
