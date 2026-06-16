#!/usr/bin/env python3
"""Regression guards for the frozen-vs-live prono consistency bug.

History: the calendar prono, the autonomous freeze and the snapshot tool each
recomputed the scoreline by hand, and two drifts crept in — making a future
match show a frozen "3-0" while the same page said "model now 2-0":

  1. the freeze called model.analyse WITHOUT attack/defense (ad_home/ad_away);
  2. the calendar used an odds-aware pick while the freeze used an odds-free one,
     so a cached odds board re-introduced the gap.

The prono now MAXIMISES expected MPP points and is deliberately odds-aware: its
base points come from the real MPP barème (data/mpp_board.json) or, as a proxy,
the *committed/cached* bookmaker odds (≈ cote×10). The invariant that prevents
the phantom-update bug is therefore no longer "model-only" but "display and
freeze read the SAME committed boards" — everything funnels through
engine.prediction.scoreline with the same mpp_board + odds_board. These tests
fail if either drift comes back, or if the odds wiring goes dead (vacuous).

Run: python3 tests/test_prediction_consistency.py   (or: python3 -m unittest)
"""
from __future__ import annotations

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

    def test_scoreline_is_deterministic(self):
        m = self.future[0]
        self.assertEqual(prediction.scoreline(m, self.ratings),
                         prediction.scoreline(m, self.ratings))
        board = {str(m.get("id", "")).upper(): [1.5, 4.0, 7.0]}
        self.assertEqual(prediction.scoreline(m, self.ratings, None, board),
                         prediction.scoreline(m, self.ratings, None, board))

    def test_calendar_prono_matches_freeze_with_same_board(self):
        """The displayed calendar prono must equal the frozen (shared-helper)
        scoreline when both are fed the SAME odds board — and also when neither
        is. This is the phantom-update guard under the odds-aware design: the two
        can only stay in lockstep by going through prediction.scoreline with the
        same inputs."""
        mpp_board = data.load_mpp_board()
        board = {str(m.get("id", "")).upper(): [1.6, 3.9, 5.4] for m in self.future}

        for odds in (board, {}):
            rows = ui._analyse_rows(self.future, self.ratings, odds, team_status=self.team_status)
            for m, r in zip(self.future, rows):
                freeze = "%d-%d" % prediction.scoreline(m, self.ratings, mpp_board, odds)
                self.assertEqual(r["predicted_score_live"], freeze,
                                 f"calendar prono != freeze for {m['home']} vs {m['away']}")

    def test_prono_is_actually_odds_aware(self):
        """Non-vacuous guard: a potent odds board MUST move the prono vs no board
        (else the EV wiring is dead and we'd be back to the modal-favourite pick
        that loses MPP)."""
        flip = [1.5, 4.0, 7.0]  # long away price -> EV pick should swing toward away
        board = {str(m.get("id", "")).upper(): list(flip) for m in self.future}
        rows_no = ui._analyse_rows(self.future, self.ratings, {}, team_status=self.team_status)
        rows_odds = ui._analyse_rows(self.future, self.ratings, board, team_status=self.team_status)
        differs = sum(1 for a, b in zip(rows_no, rows_odds)
                      if a["predicted_score_live"] != b["predicted_score_live"])
        self.assertGreater(differs, 0,
                           "odds never move the prono — EV wiring is dead (vacuous)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
