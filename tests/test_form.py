#!/usr/bin/env python3
"""Guards for the recent-form signal derived from results (engine/form.py).

Form is the model's momentum channel, kept orthogonal to Elo: it tracks the
recency-weighted W/D/L streak with a light opponent tilt, never goal margin
(which updater.apply_completed_results already owns). These tests pin that
contract — direction, bounds, recency weighting, opponent tilt, and the fact
that only the `form` field of team_status is touched.

Run: python3 -m unittest tests.test_form
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import form


def _ratings(**teams):
    return {"teams": {name: {"rating": r} for name, r in teams.items()}}


def _match(mid, home, away, gh, ga, date="2026-06-13"):
    return {"id": mid, "home": home, "away": away,
            "actual_home": gh, "actual_away": ga, "date": date}


EVEN = _ratings(A=1600.0, B=1600.0, C=1600.0)


class ComputeTeamForm(unittest.TestCase):
    def test_no_match_is_neutral(self):
        self.assertEqual(form.compute_team_form("A", [], EVEN), 0.0)

    def test_win_is_positive_loss_is_negative(self):
        win = form.compute_team_form("A", [_match("1", "A", "B", 2, 0)], EVEN)
        loss = form.compute_team_form("A", [_match("1", "A", "B", 0, 2)], EVEN)
        self.assertGreater(win, 0.0)
        self.assertLess(loss, 0.0)

    def test_draw_between_equals_is_neutral(self):
        self.assertEqual(form.compute_team_form("A", [_match("1", "A", "B", 1, 1)], EVEN), 0.0)

    def test_form_stays_in_bounds(self):
        wins = [_match(str(i), "A", "B", 3, 0, date=f"2026-06-1{i}") for i in range(1, 5)]
        self.assertLessEqual(form.compute_team_form("A", wins, EVEN), 1.0)
        losses = [_match(str(i), "A", "B", 0, 3, date=f"2026-06-1{i}") for i in range(1, 5)]
        self.assertGreaterEqual(form.compute_team_form("A", losses, EVEN), -1.0)

    def test_margin_does_not_change_form(self):
        # Elo owns goal margin; form must not. A 1-0 and a 5-0 win are the same
        # momentum from the form channel's point of view.
        narrow = form.compute_team_form("A", [_match("1", "A", "B", 1, 0)], EVEN)
        rout = form.compute_team_form("A", [_match("1", "A", "B", 5, 0)], EVEN)
        self.assertEqual(narrow, rout)

    def test_recent_match_weighs_more(self):
        # Oldest a loss, newest a win -> net positive (recency favours the win).
        seq = [_match("1", "A", "B", 0, 1, date="2026-06-11"),
               _match("2", "A", "C", 1, 0, date="2026-06-13")]
        self.assertGreater(form.compute_team_form("A", seq, EVEN), 0.0)

    def test_beating_a_stronger_side_beats_beating_a_weaker_one(self):
        ratings = _ratings(A=1600.0, Strong=1900.0, Weak=1300.0)
        vs_strong = form.compute_team_form("A", [_match("1", "A", "Strong", 1, 0)], ratings)
        vs_weak = form.compute_team_form("A", [_match("1", "A", "Weak", 1, 0)], ratings)
        self.assertGreater(vs_strong, vs_weak)


class RecomputeForm(unittest.TestCase):
    def test_updates_only_form_and_reports_changes(self):
        status = {"teams": {"A": {"form": 0.0, "injury_impact": 0.4,
                                  "news_risk": 0.2, "notes": ["x"]}}}
        _, changes = form.recompute_form(status, [_match("1", "A", "B", 2, 0)], EVEN)
        a = status["teams"]["A"]
        self.assertGreater(a["form"], 0.0)
        # Untouched ask-Claude channels.
        self.assertEqual(a["injury_impact"], 0.4)
        self.assertEqual(a["news_risk"], 0.2)
        self.assertEqual(a["notes"], ["x"])
        self.assertEqual([c[0] for c in changes], ["A", "B"])

    def test_unplayed_team_is_left_alone(self):
        status = {"teams": {"C": {"form": 0.5}}}
        _, changes = form.recompute_form(status, [_match("1", "A", "B", 2, 0)], EVEN)
        self.assertEqual(status["teams"]["C"]["form"], 0.5)
        self.assertNotIn("C", [c[0] for c in changes])

    def test_idempotent_second_run_reports_nothing(self):
        status = {"teams": {}}
        fixtures = [_match("1", "A", "B", 2, 0)]
        form.recompute_form(status, fixtures, EVEN)
        _, changes = form.recompute_form(status, fixtures, EVEN)
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
