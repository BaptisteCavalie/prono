#!/usr/bin/env python3
"""Tests for the staking planner (engine/betting.py).

Money logic -> tested (constitution). The central guarantee here: the planner
must size on the CALIBRATED 1X2, not the raw (overconfident) model grid — the
raw path manufactured fake edges and oversized stakes on short favourites, the
documented cause of the real -20% ROI. This keeps the staking planner in lockstep
with the per-match value display (engine/odds.py), which already calibrates.

Run: python3 tests/test_betting.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import betting, calibration, model


class TestEvaluateSingleUsesCalibration(unittest.TestCase):
    def test_bet_is_sized_on_calibrated_not_raw_probs(self):
        """The recommended stake must come from the calibrated 1X2.

        On an overconfident favourite the raw model claims a much bigger edge
        than the calibrated one; the planner must report the calibrated number so
        it never oversizes on fake confidence.
        """
        out = model.analyse(1750, 1550, home_adv=50)
        cal_home = calibration.calibrated_1x2(out)[0]
        bet = betting.evaluate_single(out, (1.85, 3.6, 4.2))
        self.assertIsNotNone(bet)
        self.assertEqual(bet["sel"], "home")
        # 'model' in the result is the calibrated prob, not the raw grid prob.
        self.assertAlmostEqual(bet["model"], cal_home, places=6)
        self.assertLess(bet["model"], out["p_home"],
                        "calibration must soften the raw favourite prob")

    def test_calibration_shrinks_the_stake_vs_raw(self):
        """Sizing on calibrated probs yields a strictly smaller stake than the
        old raw-prob path on the same overconfident favourite."""
        out = model.analyse(1750, 1550, home_adv=50)
        odds = (1.85, 3.6, 4.2)
        fair = model.devig(list(odds))

        def stake_frac(model_p):
            shrunk = betting.shrink_probs(model_p, fair, betting.MARKET_WEIGHT)
            return min(betting.MAX_STAKE_FRAC,
                       betting.KELLY_FRACTION * betting.kelly_fraction(shrunk[0], odds[0]))

        raw = stake_frac([out["p_home"], out["p_draw"], out["p_away"]])
        cal = stake_frac(list(calibration.calibrated_1x2(out)))
        self.assertLess(cal, raw)

    def test_no_value_returns_none(self):
        # Fairly-priced strong favourite: calibrated prob ~ fair prob -> no edge.
        out = model.analyse(1900, 1500, home_adv=60)
        self.assertIsNone(betting.evaluate_single(out, (1.40, 4.5, 8.0)))


class TestSafetyCaps(unittest.TestCase):
    def test_single_stake_never_exceeds_cap(self):
        out = model.analyse(1750, 1550, home_adv=50)
        bet = betting.evaluate_single(out, (1.85, 3.6, 4.2))
        self.assertIsNotNone(bet)
        self.assertLessEqual(bet["stake_frac"], betting.MAX_STAKE_FRAC + 1e-9)

    def test_min_odds_floor_skips_very_short_prices(self):
        out = model.analyse(2000, 1400, home_adv=60)
        # 1.20 is below MIN_ODDS (1.30): no bet regardless of edge.
        self.assertIsNone(betting.evaluate_single(out, (1.20, 6.0, 12.0)))


class TestComboFloor(unittest.TestCase):
    def _single(self, label, sel, odds, shrunk, ev):
        return {"label": label, "match_id": label,
                "bet": {"sel": sel, "odds": odds, "shrunk": shrunk, "ev": ev}}

    def test_rejects_lottery_ticket_combo(self):
        # Two thin legs (~0.40 each) compound to ~0.16 hit-rate: below the floor,
        # so no combo is suggested even if the maths is nominally +EV.
        legs = [self._single("A", "draw", 3.5, 0.40, 0.40),
                self._single("B", "draw", 3.2, 0.40, 0.28)]
        self.assertEqual(betting.build_combos(legs, 100.0), [])

    def test_keeps_solid_combo(self):
        # Two solid favourites (~0.65 each) -> ~0.42 combined, above the floor.
        legs = [self._single("A", "home", 1.7, 0.65, 0.10),
                self._single("B", "home", 1.7, 0.65, 0.10)]
        combos = betting.build_combos(legs, 100.0)
        self.assertEqual(len(combos), 1)
        self.assertGreaterEqual(combos[0]["combined_prob"],
                                betting.COMBO_MIN_COMBINED_PROB)


class TestEvaluateQualif(unittest.TestCase):
    """2-way knockout 'who advances' market staking (engine/betting.evaluate_qualif)."""

    def test_value_on_underpriced_side(self):
        # Model: home advances 62%; market prices it at 1.90 (~52% fair) -> value.
        bet = betting.evaluate_qualif(0.62, 1.90, 1.95)
        self.assertIsNotNone(bet)
        self.assertEqual(bet["sel"], "home")
        self.assertEqual(bet["market"], "qualif")
        self.assertGreater(bet["ev"], 0)
        self.assertLessEqual(bet["stake_frac"], betting.MAX_STAKE_FRAC + 1e-9)

    def test_no_value_when_fairly_priced(self):
        # Model 55% vs a 55%-implied price: no edge after the market shrink.
        self.assertIsNone(betting.evaluate_qualif(0.55, 1.82, 2.00))

    def test_rejects_out_of_range_prob(self):
        self.assertIsNone(betting.evaluate_qualif(1.4, 1.9, 1.9))
        self.assertIsNone(betting.evaluate_qualif(-0.1, 1.9, 1.9))


class TestAdvanceProb(unittest.TestCase):
    """Analytic knockout advance probability (engine/tournament.advance_prob)."""

    def _ratings(self, rh, ra):
        return {"teams": {"A": {"rating": rh}, "B": {"rating": ra}}}

    def test_even_tie_is_a_coin_flip(self):
        from engine import tournament
        p = tournament.advance_prob("A", "B", self._ratings(1700, 1700))
        self.assertAlmostEqual(p, 0.5, places=2)

    def test_favourite_advances_more_often_but_below_certainty(self):
        from engine import tournament
        p = tournament.advance_prob("A", "B", self._ratings(1900, 1500))
        self.assertGreater(p, 0.5)
        self.assertLess(p, 1.0)

    def test_complement_and_missing_team(self):
        from engine import tournament
        r = self._ratings(1850, 1600)
        p_ab = tournament.advance_prob("A", "B", r)
        p_ba = tournament.advance_prob("B", "A", r)
        # Swapping sides is ~complementary (neither is a host, so no home term).
        self.assertAlmostEqual(p_ab + p_ba, 1.0, places=2)
        self.assertIsNone(tournament.advance_prob("A", "Z", r))


if __name__ == "__main__":
    unittest.main()
