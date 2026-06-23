#!/usr/bin/env python3
"""Tests for the final-standings + Round-of-32 builder (engine/standings.py
final_standings/rank_group and tools/build_knockout_r32.compose).

Synthetic, fully-played group stage so the qualification is deterministic.

Run: python3 tests/test_knockout_r32.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import standings

# import the tool module by path (tools/ is not a package)
_spec = importlib.util.spec_from_file_location(
    "build_knockout_r32", ROOT / "tools" / "build_knockout_r32.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

GROUPS = "ABCDEFGHIJKL"
# Standard 4-team schedule by draw position (matches build_fixtures.PATTERN).
PATTERN = [(0, 1), (2, 3), (0, 2), (3, 1), (3, 0), (1, 2)]


def _result(h_pos, a_pos, teams, k):
    """Lower draw position beats higher (T1>T2>T3>T4); the 3rd-place team's GF
    grows with the group index k so the 12 thirds rank distinctly (no tie)."""
    hi, lo = min(h_pos, a_pos), max(h_pos, a_pos)
    margin = (k + 1) if (hi, lo) == (2, 3) else 1   # T3 vs T4 scoreline = (k+1)-0
    return (margin, 0) if h_pos < a_pos else (0, margin)


def _complete_fixtures():
    matches = []
    n = 1
    for k, g in enumerate(GROUPS):
        teams = [f"{g}1", f"{g}2", f"{g}3", f"{g}4"]
        for (h, a) in PATTERN:
            gh, ga = _result(h, a, teams, k)
            matches.append({
                "id": f"G{n:02d}", "stage": "group", "group": g, "matchday": 1,
                "home": teams[h], "away": teams[a],
                "actual_home": gh, "actual_away": ga,
            })
            n += 1
    return matches


# Valid third allocation for the synthetic tournament (best thirds = groups
# E..L; each third-slot match gets one of them, within its candidate set).
SEED = {"thirds_by_match": {
    "74": "F", "77": "G", "79": "H", "80": "K",
    "81": "E", "82": "I", "85": "J", "87": "L"}}


class FinalStandings(unittest.TestCase):
    def setUp(self):
        self.fx = _complete_fixtures()

    def test_complete_and_winners(self):
        st = standings.final_standings(self.fx)
        self.assertTrue(st["complete"])
        self.assertEqual(st["incomplete"], [])
        self.assertEqual(st["winners"]["A"], "A1")
        self.assertEqual(st["runners_up"]["A"], "A2")
        self.assertEqual(len(st["thirds_ranked"]), 12)

    def test_best_thirds_are_high_index_groups(self):
        st = standings.final_standings(self.fx)
        best = {g for g, _, _ in st["best_thirds"]}
        self.assertEqual(best, set("EFGHIJKL"))
        self.assertEqual(st["ties"], [])  # GF spread keeps thirds distinct

    def test_incomplete_group_skipped(self):
        # Blank out one Group A result -> group A is no longer complete.
        fx = [{**m, "actual_home": None, "actual_away": None}
              if m["id"] == "G01" else m for m in self.fx]
        st = standings.final_standings(fx)
        self.assertIn("A", st["incomplete"])
        self.assertNotIn("A", st["winners"])
        self.assertFalse(st["complete"])


class RankGroupTieBreak(unittest.TestCase):
    def test_head_to_head_breaks_equal_table(self):
        # P and Q both finish 4 pts, gd 0, gf 2 — level on every overall key.
        # Only their direct game (P beat Q 1-0) separates them.
        def g(h, a, gh, ga):
            return {"id": f"{h}{a}", "stage": "group", "group": "X",
                    "home": h, "away": a, "actual_home": gh, "actual_away": ga}
        fx = [
            g("P", "Q", 1, 0), g("P", "R", 1, 1), g("S", "P", 1, 0),
            g("Q", "R", 1, 1), g("Q", "S", 1, 0), g("R", "S", 1, 0),
        ]
        ranked, ties = standings.rank_group("X", fx)
        order = [t for t, _ in ranked]
        self.assertEqual(ties, [])
        self.assertLess(order.index("P"), order.index("Q"))


class ComposeR32(unittest.TestCase):
    def setUp(self):
        self.fx = _complete_fixtures()

    def test_resolves_all_16_no_errors(self):
        st, r32, errors = build.compose(self.fx, seed=SEED)
        self.assertEqual(errors, [])
        self.assertEqual(len(r32), 16)
        for fx in r32:
            self.assertTrue(fx["home"] and fx["away"])
            self.assertEqual(fx["stage"], "round_of_32")
        # spot-check deterministic slots and a third slot
        m73 = next(f for f in r32 if f["match_no"] == 73)
        self.assertEqual((m73["home"], m73["away"]), ("A2", "B2"))   # 2A vs 2B
        m74 = next(f for f in r32 if f["match_no"] == 74)
        self.assertEqual(m74["home"], "E1")                          # 1E
        self.assertEqual(m74["away"], "F3")                          # 3rd of group F

    def test_no_team_appears_twice(self):
        _, r32, errors = build.compose(self.fx, seed=SEED)
        teams = [t for f in r32 for t in (f["home"], f["away"])]
        self.assertEqual(len(teams), len(set(teams)))
        self.assertEqual(errors, [])

    def test_missing_third_allocation_flagged(self):
        _, _, errors = build.compose(self.fx, seed={})
        self.assertTrue(any("allocation du 3e manquante" in e for e in errors))

    def test_third_outside_candidate_set_flagged(self):
        bad = {"thirds_by_match": {**SEED["thirds_by_match"], "74": "E"}}  # E not in {A,B,C,D,F}
        _, _, errors = build.compose(self.fx, seed=bad)
        self.assertTrue(any("M74" in e and "hors des candidats" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
