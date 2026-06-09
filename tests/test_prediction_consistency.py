#!/usr/bin/env python3
"""Regression guards for the frozen-vs-live prono consistency bug.

History: the calendar prono, the autonomous freeze and the snapshot tool each
recomputed the scoreline by hand, and two drifts crept in — making a future
match show a frozen "3-0" while the same page said "model now 2-0":

  1. the freeze called model.analyse WITHOUT attack/defense (ad_home/ad_away);
  2. the calendar used odds-aware mpp.recommend(out, odds) while the freeze used
     odds-free mpp.recommend(out), so a cached odds board re-introduced the gap.

Everything now funnels through engine.prediction (model-only). These tests fail
if either drift comes back.

Run: python3 tests/test_prediction_consistency.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import data, model, mpp, prediction, team_signals, updater
import ui


def _prepared_ratings(fixtures):
    """Ratings prepared exactly like the UI / snapshot tool do."""
    ratings = data.load_ratings()
    ratings, _ = updater.apply_completed_results(ratings, fixtures)
    team_status = data.load_team_status()
    ratings = team_signals.adjust_ratings_with_status(ratings, team_status)
    return ratings, team_status


def _future(fixtures, ratings):
    teams = ratings.get("teams", {})
    return [m for m in fixtures
            if m.get("actual_home") is None and m.get("actual_away") is None
            and m.get("home") in teams and m.get("away") in teams]


class PredictionConsistency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = data.load_fixtures()
        cls.ratings, cls.team_status = _prepared_ratings(cls.fixtures)
        cls.future = _future(cls.fixtures, cls.ratings)
        assert cls.future, "expected at least one future fixture to test"

    def test_helper_uses_attack_defense(self):
        """The original freeze bug dropped attack/defense. Assert the helper
        feeds it (== explicit ad call) and that ad actually changes at least one
        scoreline vs a no-ad model, so this guard isn't vacuous."""
        differs = 0
        for m in self.future:
            rh = self.ratings["teams"][m["home"]]
            ra = self.ratings["teams"][m["away"]]
            ha = float(m.get("home_adv", 0.0) or 0.0)
            out_helper = prediction.analyse_match(m, self.ratings)
            out_explicit = model.analyse(float(rh["rating"]), float(ra["rating"]), home_adv=ha,
                                         ad_home=model.ad_from_row(rh), ad_away=model.ad_from_row(ra))
            out_no_ad = model.analyse(float(rh["rating"]), float(ra["rating"]), home_adv=ha)
            self.assertEqual(mpp.recommend(out_helper)["score"],
                             mpp.recommend(out_explicit)["score"])
            if mpp.recommend(out_helper)["score"] != mpp.recommend(out_no_ad)["score"]:
                differs += 1
        self.assertGreater(differs, 0,
                           "attack/defense never changes a scoreline — ad not wired / guard vacuous")

    def test_scoreline_is_odds_free_and_deterministic(self):
        self.assertNotIn("odds", inspect.signature(prediction.scoreline).parameters,
                         "scoreline must be model-only (no odds parameter)")
        m = self.future[0]
        self.assertEqual(prediction.scoreline(m, self.ratings),
                         prediction.scoreline(m, self.ratings))
        self.assertEqual(prediction.scoreline(m, self.ratings),
                         mpp.recommend(prediction.analyse_match(m, self.ratings))["score"])

    def test_calendar_prono_ignores_odds_and_matches_freeze(self):
        """The displayed calendar prono must equal the frozen (shared-helper)
        scoreline and must NOT move when a bookmaker odds board is present."""
        flip = [1.5, 4.0, 7.0]  # long away price -> would flip an odds-aware pick

        # Non-vacuous guard: prove this board *can* flip an odds-aware recommend.
        coin = model.analyse(1500.0, 1500.0, home_adv=0.0)
        self.assertNotEqual(mpp.recommend(coin, flip)["score"], mpp.recommend(coin)["score"],
                            "odds board is not potent enough to be a real guard")

        board = {str(m.get("id", "")).upper(): list(flip) for m in self.future}
        rows_no = ui._analyse_rows(self.future, self.ratings, {}, team_status=self.team_status)
        rows_odds = ui._analyse_rows(self.future, self.ratings, board, team_status=self.team_status)

        for m, r0, r1 in zip(self.future, rows_no, rows_odds):
            freeze = "%d-%d" % prediction.scoreline(m, self.ratings)
            self.assertEqual(r0["predicted_score_live"], freeze,
                             f"calendar prono != freeze for {m['home']} vs {m['away']}")
            self.assertEqual(r0["predicted_score_live"], r1["predicted_score_live"],
                             f"calendar prono moved with odds for {m['home']} vs {m['away']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
