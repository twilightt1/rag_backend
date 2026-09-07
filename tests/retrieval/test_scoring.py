"""Scoring tests: the decay floor keeps semantic match dominant."""
from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

from app.retrieval.memory.scoring import time_decay_score


def test_recent_memory_unchanged_by_floor():
    now = datetime.now(UTC)
    score, _ = time_decay_score(0.8, now - timedelta(days=1), now=now)
    expected = 0.8 * math.exp(-1 / 30)
    assert abs(score - expected) < 1e-9  # above the floor → pure decay


def test_old_memory_floors_instead_of_vanishing():
    now = datetime.now(UTC)
    score, reasons = time_decay_score(0.8, now - timedelta(days=1100), now=now)
    # unbounded decay would be ~1e-16; the floor keeps it at 0.1x
    assert score == 0.8 * 0.1
    assert any("decay" in r for r in reasons)


def test_floor_keeps_semantic_ordering():
    """The regression the benchmark caught: with unbounded decay, a 2023
    memory scored 1e-16 and ranking became noise (any fresh memory beat
    every old one, whatever the semantics). With the floor, the ordering
    between two equally-salient memories follows semantic match regardless
    of age."""
    now = datetime.now(UTC)
    strong_old, _ = time_decay_score(0.9, now - timedelta(days=1100), now=now)
    weak_old, _ = time_decay_score(0.2, now - timedelta(days=1100), now=now)
    assert strong_old > weak_old
    # the floor keeps old memories in the SAME order of magnitude as fresh
    # ones (0.09 vs 0.19 here) — before the fix it was 1e-16 vs 0.19, i.e.
    # total exclusion from top-k
    fresh_weak, _ = time_decay_score(0.2, now - timedelta(days=1), now=now)
    assert strong_old > fresh_weak * 0.1
