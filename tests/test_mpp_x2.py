#!/usr/bin/env python3
"""Tests for the MPP meta-game layer: 120' knockout scoring, league-position
modes, the x2 timing policy — plus regressions for two pre-kickoff bugs
(predict.py --match crash, host-as-away-team home_adv loss).

Run: python3 tests/test_mpp_x2.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import autonomous, model, mpp, x2


def _tight():
    """A near coin-flip with a real draw mass."""
    return model.analyse(1900.0, 1880.0)


def _mismatch():
    return model.analyse(2050.0, 1600.0)


class KnockoutDistribution(unittest.TestCase):
    def test_normalised_and_draws_shrink(self):
        out = _tight()
        dist = mpp.knockout_distribution(out)
        self.assertAlmostEqual(sum(dist.values()), 1.0, places=9)
        p_draw_120 = sum(p for (i, j), p in dist.items() if i == j)
        self.assertLess(p_draw_120, out["p_draw"],
                        "extra time must convert part of the 90' draw mass")
        self.assertGreater(p_draw_120, 0.0, "pens world (still level) must remain")

    def test_non_draw_scores_untouched(self):
        out = _tight()
        d90 = mpp.score_distribution(out)
        d120 = mpp.knockout_distribution(out)
        # 1-0 can only gain mass... no: 1-0 at 90' is final; ET only ADDS mass
        # to non-draw cells (from 0-0 etc.), never removes it.
        for s in ((1, 0), (0, 1), (2, 1)):
            self.assertGreaterEqual(d120[s] + 1e-12, d90[s])

    def test_recommend_knockout_outcome_probs(self):
        out = _tight()
        rec90 = mpp.recommend(out)
        rec120 = mpp.recommend(out, knockout=True)
        self.assertTrue(rec120["knockout"])
        if rec90["outcome"] == rec120["outcome"] == "home":
            self.assertGreater(rec120["p_outcome"], rec90["p_outcome"],
                               "a 90' favourite should be likelier over 120'")


class Modes(unittest.TestCase):
    def test_protect_picks_modal_in_outcome(self):
        out = _tight()
        rec = mpp.recommend(out, mode="protect")
        dist = mpp.score_distribution(out)
        best = max((s for s in dist if mpp.outcome_of(*s) == rec["outcome"]),
                   key=lambda s: dist[s])
        self.assertEqual(tuple(rec["score"]), best)

    def test_chase_targets_big_bonus(self):
        rec = mpp.recommend(_mismatch(), mode="chase")
        self.assertGreaterEqual(rec["bonus"], mpp.CHASE_MIN_BONUS)

    def test_ev_default_unchanged(self):
        out = _tight()
        self.assertEqual(mpp.recommend(out), mpp.recommend(out, mode="ev"))

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            mpp.recommend(_tight(), mode="yolo")

    def test_mode_for_position(self):
        self.assertEqual(mpp.mode_for_position(rank=1), "protect")
        self.assertEqual(mpp.mode_for_position(points_behind=120), "chase")
        self.assertEqual(mpp.mode_for_position(rank=12, total=20), "chase")
        self.assertEqual(mpp.mode_for_position(rank=5, total=20), "ev")
        self.assertEqual(mpp.mode_for_position(), "ev")


class X2Policy(unittest.TestCase):
    def test_never_md1(self):
        self.assertEqual(x2.advise("group_md1", points_behind=500)["action"], "save")

    def test_group_emergency_only(self):
        self.assertEqual(x2.advise("group")["action"], "save")
        self.assertEqual(x2.advise("group", points_behind=100)["action"], "use")

    def test_r16_optimal_unless_leading(self):
        self.assertEqual(x2.advise("r16")["action"], "use")
        self.assertEqual(x2.advise("r16", leading=True)["action"], "save")

    def test_r32_needs_standout(self):
        self.assertEqual(x2.advise("r32", best_exp=10.0)["action"], "save")
        self.assertEqual(x2.advise("r32", best_exp=60.0)["action"], "use")

    def test_endgame_forced(self):
        self.assertEqual(x2.advise("qf")["action"], "use")
        self.assertEqual(x2.advise("sf", leading=True)["action"], "use")
        self.assertEqual(x2.advise("final")["action"], "use")

    def test_invalid_stage_raises(self):
        with self.assertRaises(ValueError):
            x2.advise("eighth-finals")

    def test_best_candidate(self):
        rows = [{"home": "A", "away": "B", "rec": {"exp_points": 12.0}},
                {"home": "C", "away": "D", "rec": {"exp_points": 30.5}}]
        best = x2.best_candidate(rows)
        self.assertEqual(best["home"], "C")
        self.assertAlmostEqual(best["x2_gain"], 30.5)
        self.assertIsNone(x2.best_candidate([]))


class BugRegressions(unittest.TestCase):
    def test_predict_match_cli_works(self):
        """predict.py --match crashed (match dict missing home/away keys)."""
        r = subprocess.run(
            [sys.executable, str(ROOT / "predict.py"), "--match",
             "France vs Senegal", "--no-auto-refresh"],
            capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("MPP prono", r.stdout)

    def test_host_as_away_team_gets_home_adv(self):
        """A host listed away must get its boost as negative home_adv."""
        payload = {"matches": [
            {"home": "Türkiye", "away": "United States", "home_adv": 0.0},
            {"home": "Mexico", "away": "South Africa", "home_adv": 0.0},
            {"home": "Qatar", "away": "Bosnia-Herzegovina", "home_adv": 65.0},
        ]}
        autonomous._refresh_home_adv(payload)
        m = payload["matches"]
        self.assertEqual(m[0]["home_adv"], -autonomous.HOST_HOME_ADV)
        self.assertEqual(m[1]["home_adv"], autonomous.HOST_HOME_ADV)
        self.assertEqual(m[2]["home_adv"], autonomous.DEFAULT_HOME_ADV)


if __name__ == "__main__":
    unittest.main(verbosity=2)
