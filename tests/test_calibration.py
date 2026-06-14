#!/usr/bin/env python3
"""Regression guards for the favourite-overconfidence calibration (RATING_SHRINK).

History: the rating-only model was overconfident. On the WC2022 group stage its
1X2 logloss (1.20) was worse than a flat 33/33/33 coin (1.10), and the buckets it
priced 72-88% only won 43-71% — the same finding the betting backtest reported.
`model.RATING_SHRINK` damps the rating gap to pull that confidence toward honesty
WITHOUT flipping the favourite (accuracy is unchanged). These tests fail if the
lever is removed or stops doing its job.

Run: python3 tests/test_calibration.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import model
from tools.backtest_wc2022 import ELO_2022
from tools.backtest_wc2022_groupstage import GROUP_STAGE, HOST, HOST_ADV, outcome

_IDX = {"1": "p_home", "X": "p_draw", "2": "p_away"}


def _wc2022_mean_logloss(shrink: float) -> float:
    """Mean 1X2 logloss of the model on the 48 WC2022 group games at a given
    RATING_SHRINK (restored afterwards)."""
    saved = model.RATING_SHRINK
    model.RATING_SHRINK = shrink
    try:
        total = 0.0
        for (_md, _grp, home, away, gh, ga) in GROUP_STAGE:
            ha = HOST_ADV if home == HOST else 0.0
            out = model.analyse(ELO_2022[home], ELO_2022[away], home_adv=ha)
            p = out[_IDX[outcome(gh, ga)]]
            total += -math.log(max(p, 1e-12))
    finally:
        model.RATING_SHRINK = saved
    return total / len(GROUP_STAGE)


class Calibration(unittest.TestCase):
    def test_shrink_is_engaged(self):
        self.assertGreater(model.RATING_SHRINK, 0.0)
        self.assertLess(model.RATING_SHRINK, 1.0,
                        "RATING_SHRINK >= 1 would disable the calibration")

    def test_shrink_lowers_favourite_confidence_without_flipping_it(self):
        """For a clear mismatch the shrink pulls the favourite's win prob down,
        but the favoured outcome (argmax) must not change."""
        big = (1900.0, 1500.0)  # ~400 Elo gap: a clear home favourite
        out_shrunk = model.analyse(*big)
        saved = model.RATING_SHRINK
        model.RATING_SHRINK = 1.0
        try:
            out_raw = model.analyse(*big)
        finally:
            model.RATING_SHRINK = saved
        self.assertLess(out_shrunk["p_home"], out_raw["p_home"],
                        "shrink should reduce the favourite's win probability")
        for key in ("p_home", "p_draw", "p_away"):
            self.assertGreater(out_shrunk[key], 0.0)
        self.assertAlmostEqual(
            out_shrunk["p_home"] + out_shrunk["p_draw"] + out_shrunk["p_away"], 1.0,
            places=6)
        # argmax outcome unchanged: still a home favourite.
        self.assertEqual(max(("p_home", "p_draw", "p_away"), key=out_shrunk.get),
                         "p_home")

    def test_shrink_improves_wc2022_logloss(self):
        """The whole point: calibrated probs score a better (lower) logloss on
        the WC2022 group stage than the raw, unshrunk model."""
        self.assertLess(_wc2022_mean_logloss(model.RATING_SHRINK),
                        _wc2022_mean_logloss(1.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
