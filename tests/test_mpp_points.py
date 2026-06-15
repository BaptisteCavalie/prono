#!/usr/bin/env python3
"""Guards for the real-barème MPP pick + the "gros lot" alternative.

`mpp.recommend(out, mpp_points=...)` must pick the outcome that maximises
expected MPP points using the REAL points (not the odds≈cote×10 proxy), and
`mpp.upside_pick` must surface the best *alternative* gamble for a trailing
player — never the safe favourite, never a sub-floor lottery.

Run: python3 tests/test_mpp_points.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import model, mpp


class MppPoints(unittest.TestCase):
    def setUp(self):
        # A clear-ish home favourite, still a real distribution (draw/away alive).
        self.fav = model.analyse(1700.0, 1500.0)
        # A near-certain home favourite: draw and away both below the upside floor.
        self.crush = model.analyse(2200.0, 1200.0)

    def test_points_flip_outcome_to_the_payer(self):
        """When the draw pays vastly more, the points-optimal pick IS the draw,
        even though the model favours home — that's the whole barème logic."""
        rec = mpp.recommend(self.fav, mpp_points=[1, 1000, 1])
        self.assertEqual(rec["outcome"], "draw")
        # And when the favourite pays most, it stays home.
        rec_fav = mpp.recommend(self.fav, mpp_points=[1000, 1, 1])
        self.assertEqual(rec_fav["outcome"], "home")

    def test_real_points_beat_the_odds_proxy_path(self):
        """Passing mpp_points must drive the pick, not the odds proxy: with rich
        draw points the pick is the draw regardless of any odds also supplied."""
        rec = mpp.recommend(self.fav, odds=[1.10, 8.0, 20.0], mpp_points=[1, 1000, 1])
        self.assertEqual(rec["outcome"], "draw")
        self.assertEqual(rec["base_points"], 1000)

    def test_upside_is_the_best_non_favourite_gamble(self):
        points = [10, 100, 100]
        ev = mpp.recommend(self.fav, mpp_points=points)
        up = mpp.upside_pick(self.fav, points)
        self.assertIsNotNone(up)
        # The gros lot is never the safe expected-points pick…
        self.assertNotEqual(up["outcome"], ev["outcome"])
        # …it clears the plausibility floor…
        self.assertGreaterEqual(up["p_outcome"], mpp.UPSIDE_MIN_PROB)
        # …and it is the highest-E[points] outcome among the alternatives.
        p_out = {"home": self.fav["p_home"], "draw": self.fav["p_draw"],
                 "away": self.fav["p_away"]}
        base = dict(zip(("home", "draw", "away"), points))
        alts = [o for o in ("home", "draw", "away")
                if o != ev["outcome"] and p_out[o] >= mpp.UPSIDE_MIN_PROB]
        best = max(alts, key=lambda o: p_out[o] * base[o])
        self.assertEqual(up["outcome"], best)

    def test_no_upside_when_only_the_favourite_is_plausible(self):
        """A near-certain favourite leaves no sane catch-up gamble -> None."""
        self.assertIsNone(mpp.upside_pick(self.crush, [100, 100, 100]))

    def test_upside_score_is_the_most_likely_in_its_outcome(self):
        """The gros lot picks the most likely score of its contrarian outcome
        (it gambles on the OUTCOME, not on a rare scoreline) — so its copy must
        not sell it as a rare-score / X2 play."""
        up = mpp.upside_pick(self.fav, [10, 100, 100])
        self.assertIsNotNone(up)
        dist = mpp.score_distribution(self.fav)
        in_outcome = [(s, p) for s, p in dist.items()
                      if mpp.outcome_of(*s) == up["outcome"]]
        best_score = max(in_outcome, key=lambda sp: sp[1])[0]
        self.assertEqual(up["score"], best_score)

    def test_no_points_matches_model_only(self):
        """mpp_points=None must reproduce the historical model-only pick exactly,
        so loading no board is a silent, safe fallback."""
        self.assertEqual(mpp.recommend(self.fav, mpp_points=None)["score"],
                         mpp.recommend(self.fav)["score"])
        self.assertEqual(mpp.recommend(self.fav, mpp_points=None)["outcome"],
                         mpp.recommend(self.fav)["outcome"])

    def test_no_points_means_no_upside(self):
        self.assertIsNone(mpp.upside_pick(self.fav, None))
        self.assertIsNone(mpp.upside_pick(self.fav, []))


if __name__ == "__main__":
    unittest.main(verbosity=2)
