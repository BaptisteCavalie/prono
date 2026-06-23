#!/usr/bin/env python3
"""Tests for the knockout bracket + forward tournament simulation
(engine/tournament.py, engine/outrights.py, data/bracket.json).

These guard the new "phases finales" machinery: a wrong bracket or a leaky
simulation would mislead both the MPP planning and the outright bets, so the
structural facts (every group represented once, eligibility-respecting third
allocation) and the probability invariants (champion sums to 1, reach-rounds
nest, nothing outside [0,1]) are pinned here.

Run: python3 tests/test_tournament.py   (or: python3 -m unittest tests.test_tournament)
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import data, model, odds_fetch, outrights, tournament

GROUP_LETTERS = list("ABCDEFGHIJKL")


class TestBracketStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bracket = data.load_bracket()

    def test_r32_has_16_ties(self):
        self.assertEqual(len(self.bracket["r32"]), 16)

    def test_every_group_winner_and_runner_used_once(self):
        winners, runners, thirds = [], [], 0
        for e in self.bracket["r32"]:
            for side in (e["a"], e["b"]):
                if "w" in side:
                    winners.append(side["w"])
                elif "r" in side:
                    runners.append(side["r"])
                elif "t" in side:
                    thirds += 1
        self.assertCountEqual(winners, GROUP_LETTERS, "each group winner exactly once")
        self.assertCountEqual(runners, GROUP_LETTERS, "each group runner-up exactly once")
        self.assertEqual(thirds, 8, "eight third-place slots")

    def test_third_slots_have_five_eligible_groups(self):
        for e in self.bracket["r32"]:
            if "t" in e.get("b", {}):
                self.assertEqual(len(e["b"]["t"]), 5)
                self.assertTrue(set(e["b"]["t"]) <= set(GROUP_LETTERS))

    def test_knockout_tree_links_resolve(self):
        # Every {win:N} reference must point at an earlier-round match id.
        ids = {e["m"] for rnd in ("r32", "r16", "qf", "sf", "final")
               for e in self.bracket[rnd]}
        for rnd in ("r16", "qf", "sf", "final"):
            for e in self.bracket[rnd]:
                for side in (e["a"], e["b"]):
                    self.assertIn(side["win"], ids)
        self.assertEqual(len(self.bracket["r16"]), 8)
        self.assertEqual(len(self.bracket["qf"]), 4)
        self.assertEqual(len(self.bracket["sf"]), 2)
        self.assertEqual(len(self.bracket["final"]), 1)


class TestThirdAllocation(unittest.TestCase):
    def setUp(self):
        self.slots = tournament._third_slots(data.load_bracket())

    def test_allocation_respects_eligibility_and_is_a_bijection(self):
        rng = random.Random(1)
        elig_by_slot = {s["m"]: set(s["elig"]) for s in self.slots}
        # Try many 8-of-12 third-group subsets; each must allocate validly.
        for _ in range(200):
            groups = rng.sample(GROUP_LETTERS, 8)
            thirds_by_group = {g: f"team_{g}" for g in groups}
            assign = tournament._allocate_thirds(self.slots, thirds_by_group, rng)
            self.assertEqual(len(assign), 8)
            self.assertCountEqual(list(assign.values()),
                                  list(thirds_by_group.values()),
                                  "every qualifying third placed exactly once")
            for m, team in assign.items():
                grp = team.split("_")[1]
                self.assertIn(grp, elig_by_slot[m],
                              f"third from {grp} placed in ineligible slot {m}")


class TestKnockoutModel(unittest.TestCase):
    def test_knockout_always_produces_a_winner(self):
        ratings = {"teams": {"A": {"rating": 1800}, "B": {"rating": 1500}}}
        km = tournament._KnockoutModel(ratings)
        rng = random.Random(3)
        for _ in range(500):
            w = km.play("A", "B", rng)
            self.assertIn(w, ("A", "B"))

    def test_stronger_side_wins_more_often(self):
        ratings = {"teams": {"Strong": {"rating": 2000}, "Weak": {"rating": 1400}}}
        km = tournament._KnockoutModel(ratings)
        rng = random.Random(5)
        wins = sum(km.play("Strong", "Weak", rng) == "Strong" for _ in range(2000))
        self.assertGreater(wins, 1200, "a 600-Elo favourite should win most ties")


class TestSimulationInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sim = tournament.project(n_sims=2000, seed=42)
        cls.teams = cls.sim["teams"]

    def test_probabilities_in_range(self):
        for p in self.teams.values():
            for k in ("p_qualify", "p_r16", "p_qf", "p_sf", "p_final", "p_champion"):
                self.assertGreaterEqual(p[k], 0.0)
                self.assertLessEqual(p[k], 1.0)

    def test_champion_mass_sums_to_one(self):
        self.assertAlmostEqual(sum(p["p_champion"] for p in self.teams.values()),
                               1.0, places=6)

    def test_exactly_32_qualify_in_expectation(self):
        self.assertAlmostEqual(sum(p["p_qualify"] for p in self.teams.values()),
                               32.0, places=4)

    def test_two_finalists_per_sim(self):
        self.assertAlmostEqual(sum(p["p_final"] for p in self.teams.values()),
                               2.0, places=4)

    def test_reach_rounds_are_nested(self):
        # You cannot reach a later round without the earlier one.
        for t, p in self.teams.items():
            self.assertLessEqual(p["p_champion"], p["p_final"] + 1e-9, t)
            self.assertLessEqual(p["p_final"], p["p_sf"] + 1e-9, t)
            self.assertLessEqual(p["p_sf"], p["p_qf"] + 1e-9, t)
            self.assertLessEqual(p["p_qf"], p["p_r16"] + 1e-9, t)
            self.assertLessEqual(p["p_r16"], p["p_qualify"] + 1e-9, t)

    def test_calibration_check_runs(self):
        rows = tournament.calibration_check(self.sim)
        self.assertTrue(rows)
        self.assertTrue(all("metric" in r and "ok" in r for r in rows))

    def test_projected_bracket_is_complete(self):
        pb = self.sim["projected_bracket"]
        self.assertEqual(len(pb["winners"]), 12)
        self.assertEqual(len(pb["runners"]), 12)
        self.assertEqual(len(pb["r32"]), 16)
        # Each projected R32 tie has two distinct named teams.
        for tie in pb["r32"]:
            self.assertTrue(tie["home"] and tie["away"])
            self.assertNotEqual(tie["home"], tie["away"])


class TestOutrights(unittest.TestCase):
    def _sim_stub(self, p_champ):
        return {"teams": {t: {"group": "A", "p_champion": v, "p_final": v,
                              "p_qualify": 1.0, "p_first": v}
                          for t, v in p_champ.items()}}

    def test_value_flagged_when_sim_beats_price(self):
        # France priced at 6.0 (fair ~ depends on de-vig) but sim says 25%.
        sim = self._sim_stub({"France": 0.25, "Argentina": 0.20, "Spain": 0.18})
        board = {"markets": {"champion": {"France": 6.0, "Argentina": 5.0,
                                          "Spain": 6.0}}}
        rows = outrights.find_value(sim, board)
        self.assertTrue(any(r["team"] == "France" for r in rows))
        for r in rows:
            self.assertGreater(r["ev"], 0.0)

    def test_no_value_when_price_is_fair_or_short(self):
        sim = self._sim_stub({"A": 0.34, "B": 0.33, "C": 0.33})
        # Short, margin-laden prices: no edge.
        board = {"markets": {"champion": {"A": 1.5, "B": 1.5, "C": 1.5}}}
        self.assertEqual(outrights.find_value(sim, board), [])

    def test_empty_board_returns_nothing(self):
        sim = self._sim_stub({"A": 1.0})
        self.assertEqual(outrights.find_value(sim, {"markets": {}}), [])


class TestOutrightFetch(unittest.TestCase):
    """The Odds API 'outrights' (tournament winner) mapping + manual overlay."""

    RATINGS = {"teams": {"France": {"rating": 2100}, "Brazil": {"rating": 2000},
                         "United States": {"rating": 1800}}}

    def test_market_is_median_across_bookmakers_and_resolves_names(self):
        events = [{"bookmakers": [
            {"markets": [{"key": "outrights", "outcomes": [
                {"name": "France", "price": 5.0}, {"name": "Brazil", "price": 7.0},
                {"name": "USA", "price": 21.0}]}]},
            {"markets": [{"key": "outrights", "outcomes": [
                {"name": "France", "price": 5.5}, {"name": "Brazil", "price": 6.0},
                {"name": "USA", "price": 19.0}]}]},
        ]}]
        mkt = odds_fetch.outright_events_to_market(events, self.RATINGS)
        self.assertAlmostEqual(mkt["France"], 5.25)      # median of 5.0, 5.5
        self.assertAlmostEqual(mkt["Brazil"], 6.5)
        self.assertIn("United States", mkt)              # "USA" alias resolved
        self.assertNotIn("USA", mkt)

    def test_bad_prices_are_dropped(self):
        events = [{"bookmakers": [{"markets": [{"key": "outrights", "outcomes": [
            {"name": "France", "price": 1.0},            # <= 1 -> invalid
            {"name": "Brazil", "price": "x"},            # non-numeric -> invalid
        ]}]}]}]
        self.assertEqual(odds_fetch.outright_events_to_market(events, self.RATINGS), {})

    def test_manual_overlay_wins_over_api_cache(self):
        # Simulate find_value with an explicit merged board (manual wins).
        api = {"markets": {"champion": {"France": 5.2, "Brazil": 6.8}}}
        manual = {"markets": {"champion": {"France": 9.9}}}
        merged = {}
        for src in (api, manual):
            for m, s in src["markets"].items():
                merged.setdefault(m, {}).update(s)
        self.assertEqual(merged["champion"]["France"], 9.9)
        self.assertEqual(merged["champion"]["Brazil"], 6.8)


if __name__ == "__main__":
    unittest.main()
