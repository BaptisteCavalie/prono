#!/usr/bin/env python3
"""Guard: a match cannot be 'completed' before its kickoff.

History: the autonomous /maj-resultats job once wrote a score for a match ~12h
before kickoff (G63 Portugal-Uzbekistan, and earlier G45 Spain-Saudi Arabia),
because it targeted matches by *calendar date* rather than kickoff time. The UI
flagged any match with a score as 'terminé', so a future match showed as played
with a fabricated score. ``common.kickoff_in_future`` is the shared safety net,
used by both ``ui._is_completed`` and ``engine.standings._is_completed``.

Run: python3 -m unittest tests.test_completed_guard
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui
from engine import common, standings

# Unambiguously past / future relative to any plausible wall clock running these.
PAST = "2000-01-01T00:00:00Z"
FUTURE = "2999-01-01T00:00:00Z"


class KickoffInFuture(unittest.TestCase):
    NOW = datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc)

    def test_future_kickoff_is_future(self):
        m = {"kickoff_utc": "2026-06-23T17:00:00Z"}
        self.assertTrue(common.kickoff_in_future(m, now=self.NOW))

    def test_past_kickoff_is_not_future(self):
        m = {"kickoff_utc": "2026-06-21T16:00:00Z"}
        self.assertFalse(common.kickoff_in_future(m, now=self.NOW))

    def test_missing_or_bad_kickoff_does_not_block(self):
        # Unknown kickoff -> we don't decide (False), so completion still trusts
        # actual_* and nothing breaks for fixtures without a committed kickoff.
        self.assertFalse(common.kickoff_in_future({}, now=self.NOW))
        self.assertFalse(common.kickoff_in_future({"kickoff_utc": "n/a"}, now=self.NOW))


class CompletedGuard(unittest.TestCase):
    def test_future_kickoff_with_score_is_not_completed(self):
        m = {"actual_home": 1, "actual_away": 0, "kickoff_utc": FUTURE}
        self.assertFalse(ui._is_completed(m))
        self.assertFalse(standings._is_completed(m))

    def test_past_kickoff_with_score_is_completed(self):
        m = {"actual_home": 1, "actual_away": 0, "kickoff_utc": PAST}
        self.assertTrue(ui._is_completed(m))
        self.assertTrue(standings._is_completed(m))

    def test_no_kickoff_with_score_stays_completed(self):
        m = {"actual_home": 1, "actual_away": 0}
        self.assertTrue(ui._is_completed(m))
        self.assertTrue(standings._is_completed(m))

    def test_no_score_is_not_completed(self):
        m = {"actual_home": None, "actual_away": None, "kickoff_utc": PAST}
        self.assertFalse(ui._is_completed(m))
        self.assertFalse(standings._is_completed(m))


if __name__ == "__main__":
    unittest.main(verbosity=2)
