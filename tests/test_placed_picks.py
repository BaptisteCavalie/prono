#!/usr/bin/env python3
"""Guards for the « déjà joué » badge logic (ui._placed_picks).

The Paris tab marks recommended bets Baptiste has already taken on Winamax so
he sees what's left to do. The trap: a *combiné* must only be flagged when that
combiné itself was played — NOT when its legs happen to have been played
separately as singles (jouer Iran et Mexique en simples ≠ avoir joué le combiné
Iran+Mexique). Showing a false « déjà joué » would make him skip a bet he meant
to take, defeating the feature. Crossed by fixture id.

Run: python3 -m unittest tests.test_placed_picks
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui


class PlacedPicks(unittest.TestCase):
    def test_single_goes_to_singles(self):
        bets = [{"legs": [{"match": "G37", "pick": "home"}]}]
        placed = ui._placed_picks(bets)
        self.assertIn(("G37", "home"), placed["singles"])
        self.assertEqual(placed["combos"], set())

    def test_combo_goes_to_combos_as_a_whole(self):
        bets = [{"combo": True, "legs": [
            {"match": "G21", "pick": "draw"}, {"match": "G48", "pick": "draw"}]}]
        placed = ui._placed_picks(bets)
        self.assertEqual(placed["singles"], set())
        self.assertIn(frozenset({("G21", "draw"), ("G48", "draw")}), placed["combos"])

    def test_combo_inferred_from_two_legs_without_flag(self):
        # même sans champ ``combo``, deux jambes = un combiné.
        bets = [{"legs": [
            {"match": "G02", "pick": "home"}, {"match": "G24", "pick": "away"}]}]
        placed = ui._placed_picks(bets)
        self.assertEqual(placed["singles"], set())
        self.assertIn(frozenset({("G02", "home"), ("G24", "away")}), placed["combos"])

    def test_legs_played_as_singles_do_NOT_make_a_combo(self):
        # le cœur du bug corrigé : Iran (simple) + Mexique (simple) ne couvrent
        # PAS le combiné Iran+Mexique.
        bets = [
            {"legs": [{"match": "G99", "pick": "home"}]},   # Iran simple
            {"legs": [{"match": "G03", "pick": "home"}]},   # Mexique simple
        ]
        placed = ui._placed_picks(bets)
        combo_key = frozenset({("G99", "home"), ("G03", "home")})
        self.assertNotIn(combo_key, placed["combos"])
        self.assertEqual(placed["combos"], set())
        self.assertEqual(placed["singles"], {("G99", "home"), ("G03", "home")})

    def test_case_insensitive_match_ids(self):
        bets = [{"legs": [{"match": "g37", "pick": "home"}]}]
        self.assertIn(("G37", "home"), ui._placed_picks(bets)["singles"])

    def test_no_legs_or_empty_is_neutral(self):
        placed = ui._placed_picks([{"status": "gagne"}, {}, {"legs": []}])
        self.assertEqual(placed["singles"], set())
        self.assertEqual(placed["combos"], set())

    def test_none_is_neutral(self):
        placed = ui._placed_picks(None)
        self.assertEqual(placed, {"singles": set(), "combos": set()})


if __name__ == "__main__":
    unittest.main()
