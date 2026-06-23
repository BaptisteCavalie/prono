#!/usr/bin/env python3
"""Tests for the competition-state ('stakes') layer (engine/standings.py).

Synthetic groups so the cases are deterministic (data/fixtures.json moves daily).

Run: python3 tests/test_standings.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import standings


def _match(mid, group, home, away, gh=None, ga=None, stage="group"):
    return {"id": mid, "group": group, "stage": stage,
            "home": home, "away": away, "actual_home": gh, "actual_away": ga}


def _group_md3(group, p1, p2, p3, p4, results_md12, remaining):
    """Two played rounds + the MD3 pair, for a 4-team group [p1..p4]."""
    fx = []
    for i, (h, a, gh, ga) in enumerate(results_md12):
        fx.append(_match(f"{group}{i}", group, h, a, gh, ga))
    for i, (h, a) in enumerate(remaining):
        fx.append(_match(f"{group}R{i}", group, h, a))
    return fx


class GroupTable(unittest.TestCase):
    def test_points_and_gd(self):
        fx = [
            _match("X1", "X", "A", "B", 2, 0),   # A win
            _match("X2", "X", "C", "D", 1, 1),   # draw
            _match("X3", "X", "A", "C"),         # remaining
        ]
        teams, remaining = standings.group_table("X", fx)
        self.assertEqual(teams["A"]["pts"], 3)
        self.assertEqual(teams["A"]["gd"], 2)
        self.assertEqual(teams["C"]["pts"], 1)
        self.assertEqual(remaining, [("A", "C")])


class Status(unittest.TestCase):
    def _two_clear_leaders_group(self):
        # P1,P2 on 6 pts; P3,P4 on 0. MD3: P3 v P4 (loser pair), P1 v P2 (leaders).
        return [
            _match("G1", "G", "P1", "P3", 3, 0),
            _match("G2", "G", "P2", "P4", 3, 0),
            _match("G3", "G", "P1", "P4", 3, 0),
            _match("G4", "G", "P2", "P3", 3, 0),
            _match("G5", "G", "P3", "P4"),   # both already out
            _match("G6", "G", "P1", "P2"),   # both already through
        ]

    def test_qualified_when_top2_locked(self):
        fx = self._two_clear_leaders_group()
        self.assertEqual(standings.team_status("P1", "G", fx), standings.QUALIFIED)
        self.assertEqual(standings.team_status("P2", "G", fx), standings.QUALIFIED)

    def test_eliminated_when_cannot_reach_top2_or_third_bar(self):
        fx = self._two_clear_leaders_group()
        # P3/P4 max out at 3 pts, below the third-place bar, and can't pass P1/P2.
        self.assertEqual(standings.team_status("P3", "G", fx), standings.ELIMINATED)
        self.assertEqual(standings.team_status("P4", "G", fx), standings.ELIMINATED)

    def test_contention_when_result_still_matters(self):
        # Symmetric group: all four on 3 pts after two rounds, each plays a team
        # it hasn't met on MD3 — everyone can still finish top 2 or bottom 2.
        fx = [
            _match("C1", "C", "A", "B", 2, 0),   # A beats B
            _match("C2", "C", "C", "D", 1, 0),   # C beats D
            _match("C3", "C", "D", "A", 1, 0),   # D beats A
            _match("C4", "C", "B", "C", 1, 0),   # B beats C
            _match("C5", "C", "A", "C"),         # remaining (unmet pair)
            _match("C6", "C", "B", "D"),         # remaining (unmet pair)
        ]
        for t in ("A", "B", "C", "D"):
            self.assertEqual(standings.team_status(t, "C", fx), standings.CONTENTION)


class StakesFor(unittest.TestCase):
    def setUp(self):
        self.fx = [
            _match("G1", "G", "P1", "P3", 3, 0),
            _match("G2", "G", "P2", "P4", 3, 0),
            _match("G3", "G", "P1", "P4", 3, 0),
            _match("G4", "G", "P2", "P3", 3, 0),
            _match("G5", "G", "P3", "P4"),   # eliminated vs eliminated -> dead rubber
            _match("G6", "G", "P1", "P2"),   # qualified vs qualified -> dead rubber
        ]

    def test_dead_rubber_both_qualified(self):
        m = next(x for x in self.fx if x["id"] == "G6")
        s = standings.stakes_for(m, self.fx)
        self.assertTrue(s["dead_rubber"])
        self.assertEqual(s["delta_home"], standings.QUALIFIED_MALUS)
        self.assertEqual(s["delta_away"], standings.QUALIFIED_MALUS)

    def test_dead_rubber_both_eliminated(self):
        m = next(x for x in self.fx if x["id"] == "G5")
        s = standings.stakes_for(m, self.fx)
        self.assertTrue(s["dead_rubber"])
        self.assertEqual(s["delta_home"], standings.ELIMINATED_MALUS)

    def test_completed_match_has_no_stakes(self):
        m = next(x for x in self.fx if x["id"] == "G1")
        s = standings.stakes_for(m, self.fx)
        self.assertEqual(s["delta_home"], 0.0)
        self.assertEqual(s["delta_away"], 0.0)
        self.assertFalse(s["dead_rubber"])

    def test_knockout_stage_has_no_stakes(self):
        ko = _match("K1", "", "A", "B", stage="r32")
        s = standings.stakes_for(ko, self.fx)
        self.assertEqual(s["delta_home"], 0.0)

    def test_apply_stakes_nudges_only_when_needed(self):
        ratings = {"teams": {"P1": {"rating": 1800.0}, "P2": {"rating": 1700.0},
                             "P3": {"rating": 1600.0}, "P4": {"rating": 1500.0}}}
        played = next(x for x in self.fx if x["id"] == "G1")
        same, _ = standings.apply_stakes(ratings, played, self.fx)
        self.assertIs(same, ratings)  # no copy on the no-op path

        dead = next(x for x in self.fx if x["id"] == "G6")
        adj, stakes = standings.apply_stakes(ratings, dead, self.fx)
        self.assertIsNot(adj, ratings)
        self.assertEqual(adj["teams"]["P1"]["rating"],
                         1800.0 + standings.QUALIFIED_MALUS)
        self.assertEqual(ratings["teams"]["P1"]["rating"], 1800.0)  # input untouched


if __name__ == "__main__":
    unittest.main(verbosity=2)
