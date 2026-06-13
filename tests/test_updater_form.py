#!/usr/bin/env python3
"""Guards for the in-tournament form update (engine/updater.py).

History: the goal-difference multiplier was log(|goal_diff| + 1), which is 0 for
a draw, so every drawn result moved ratings by exactly nothing — a held
favourite (a clear under-performance) was invisible to the model. These tests
pin the fix: draws now carry a modest floor, decisive wins are unchanged, and an
under-dog over-performing gains more than a favourite meeting expectation.

Run: python3 -m unittest tests.test_updater_form
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import updater


def _ratings(a: float, b: float):
    return {"teams": {"A": {"rating": a}, "B": {"rating": b}}}


def _match(gh: int, ga: int, home_adv: float = 0.0):
    return {"id": "T", "home": "A", "away": "B", "date": "2026-06-13",
            "actual_home": gh, "actual_away": ga, "home_adv": home_adv}


class GoalMultiplier(unittest.TestCase):
    def test_draw_is_no_longer_zero(self):
        self.assertGreater(updater._goal_mult(0, 200.0), 0.0)

    def test_draw_weighs_less_than_a_one_goal_win(self):
        rd = 200.0
        self.assertLess(updater._goal_mult(0, rd), updater._goal_mult(1, rd))

    def test_wins_are_not_inflated(self):
        # For any decisive margin the multiplier is still the pure log path
        # (log(2) >= DRAW_MARGIN), i.e. the fix touches draws only.
        rd = 200.0
        factor = 2.2 / (abs(rd) * 0.001 + 2.2)
        self.assertAlmostEqual(updater._goal_mult(1, rd), math.log(2.0) * factor)
        self.assertAlmostEqual(updater._goal_mult(3, rd), math.log(4.0) * factor)


class ApplyCompletedResults(unittest.TestCase):
    def test_surprising_draw_moves_ratings(self):
        # Favourite A (1800) held to a draw by under-dog B (1500): A must drop,
        # B must rise. Before the fix this delta was exactly 0.
        out, n = updater.apply_completed_results(_ratings(1800.0, 1500.0), [_match(1, 1)])
        self.assertEqual(n, 1)
        self.assertLess(out["teams"]["A"]["rating"], 1800.0)
        self.assertGreater(out["teams"]["B"]["rating"], 1500.0)

    def test_underdog_win_beats_favourite_expectation(self):
        # "World Cup magic": an under-dog (1500) beating a favourite (1800) gains
        # more than a favourite (1800) beating an equal under-dog (1500) — the
        # reward scales with how unexpected the result was.
        upset, _ = updater.apply_completed_results(_ratings(1500.0, 1800.0), [_match(1, 0)])
        underdog_gain = upset["teams"]["A"]["rating"] - 1500.0

        expected, _ = updater.apply_completed_results(_ratings(1800.0, 1500.0), [_match(1, 0)])
        favourite_gain = expected["teams"]["A"]["rating"] - 1800.0

        self.assertGreater(underdog_gain, favourite_gain)


if __name__ == "__main__":
    unittest.main(verbosity=2)
