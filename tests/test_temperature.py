#!/usr/bin/env python3
"""Tests for the 1X2 temperature calibration layer (engine/calibration.py).

The layer softens the model's overconfident probabilities without ever flipping
the favourite. These guard the three properties that make it safe and useful:
  1. monotone — the argmax (the pick) is preserved, so accuracy can't change;
  2. softening — T>1 lowers the top probability and lifts the others;
  3. it earns its keep — calibrated probs score a better (lower) log-loss than the
     raw model on the WC2022 group stage (out-of-sample vs the WC2026 fit).

Run: python3 tests/test_temperature.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import calibration, model
from tools.backtest_wc2022 import ELO_2022
from tools.backtest_wc2022_groupstage import GROUP_STAGE, HOST, HOST_ADV, outcome

_IDX = {"1": 0, "X": 1, "2": 2}


class Temperature(unittest.TestCase):
    def test_default_is_engaged(self):
        self.assertGreater(calibration.CALIBRATION_T, 1.0,
                           "T <= 1 would disable the softening")

    def test_identity_at_T1(self):
        p = [0.6, 0.25, 0.15]
        out = calibration.temper(p, 1.0)
        for a, b in zip(out, p):
            self.assertAlmostEqual(a, b, places=9)

    def test_rejects_non_positive_temperature(self):
        with self.assertRaises(ValueError):
            calibration.temper([0.5, 0.3, 0.2], 0.0)
        with self.assertRaises(ValueError):
            calibration.temper([0.5, 0.3, 0.2], -1.0)

    def test_softens_and_renormalises(self):
        p = [0.90, 0.07, 0.03]
        q = calibration.temper(p, 1.5)
        self.assertAlmostEqual(sum(q), 1.0, places=9)
        self.assertLess(q[0], p[0], "top probability should come down")
        self.assertGreater(q[1], p[1], "other outcomes should come up")
        self.assertGreater(q[2], p[2])

    def test_argmax_preserved(self):
        # A clear home favourite stays a home favourite after calibration.
        out = model.analyse(1900.0, 1500.0)
        h, d, a = calibration.calibrated_1x2(out)
        self.assertEqual(max(range(3), key=lambda i: (h, d, a)[i]), 0)
        self.assertAlmostEqual(h + d + a, 1.0, places=9)

    def test_handles_degenerate_inputs(self):
        self.assertEqual(calibration.temper([], 1.5), [])
        # an all-zero vector is returned as-is rather than dividing by zero
        self.assertEqual(calibration.temper([0.0, 0.0, 0.0], 1.5), [0.0, 0.0, 0.0])

    def test_calibrated_probs_keys(self):
        out = model.analyse(1800.0, 1700.0)
        d = calibration.calibrated_probs(out)
        self.assertEqual(set(d), {"home", "draw", "away"})
        self.assertAlmostEqual(sum(d.values()), 1.0, places=9)

    def _wc2022_logloss(self, temperature) -> float:
        total = 0.0
        for (_md, _grp, home, away, gh, ga) in GROUP_STAGE:
            ha = HOST_ADV if home == HOST else 0.0
            out = model.analyse(ELO_2022[home], ELO_2022[away], home_adv=ha)
            p = calibration.temper(
                [out["p_home"], out["p_draw"], out["p_away"]], temperature)
            total += -math.log(max(p[_IDX[outcome(gh, ga)]], 1e-12))
        return total / len(GROUP_STAGE)

    def test_improves_wc2022_logloss_out_of_sample(self):
        """T was fit on WC2026; it must still lower log-loss on WC2022."""
        self.assertLess(self._wc2022_logloss(calibration.CALIBRATION_T),
                        self._wc2022_logloss(1.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
