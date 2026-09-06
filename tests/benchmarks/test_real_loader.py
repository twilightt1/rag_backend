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
