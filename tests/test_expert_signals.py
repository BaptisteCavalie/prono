#!/usr/bin/env python3
"""Unit guards for the expert-prior layer (engine/expert_signals.py).

Wiloo (or any pundit) is a *bounded, auditable nudge*, never an override. These
tests lock the delta math, the clamping, and the no-op-when-empty contract so a
future change can't silently let an expert overturn the statistical model.

Run: python3 tests/test_expert_signals.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import expert_signals as es


def _src(teams, trust=1.0, cap=35.0):
    return {"source": "test", "label": "Test", "trust": trust,
            "cap_elo": cap, "teams": teams}


class TeamDeltaMath(unittest.TestCase):
    def test_max_conviction_hits_cap(self):
        src = _src({"France": {"lean": 2, "confidence": 1.0}})
        self.assertEqual(es.team_delta("France", [src]), 35.0)

    def test_negative_lean_goes_negative(self):
        src = _src({"Germany": {"lean": -2, "confidence": 1.0}})
        self.assertEqual(es.team_delta("Germany", [src]), -35.0)

    def test_scales_with_lean_and_confidence(self):
        # lean/2 * confidence * trust * cap = 0.5 * 0.5 * 1 * 35
        src = _src({"Morocco": {"lean": 1, "confidence": 0.5}})
        self.assertAlmostEqual(es.team_delta("Morocco", [src]), 8.75)

    def test_trust_dials_it_down(self):
        src = _src({"France": {"lean": 2, "confidence": 1.0}}, trust=0.5)
        self.assertEqual(es.team_delta("France", [src]), 17.5)

    def test_out_of_range_inputs_are_clamped(self):
        src = _src({"France": {"lean": 9, "confidence": 9}})
        self.assertEqual(es.team_delta("France", [src]), 35.0)

    def test_unknown_team_is_zero(self):
        src = _src({"France": {"lean": 2, "confidence": 1.0}})
        self.assertEqual(es.team_delta("Spain", [src]), 0.0)

    def test_global_cap_bounds_stacked_sources(self):
        # Two sources each maxed (+35) would be +70, but GLOBAL_CAP_ELO=60.
        a = _src({"France": {"lean": 2, "confidence": 1.0}})
        b = _src({"France": {"lean": 2, "confidence": 1.0}})
        self.assertEqual(es.team_delta("France", [a, b]), es.GLOBAL_CAP_ELO)


class ApplyToRatings(unittest.TestCase):
    def test_noop_when_no_sources(self):
        ratings = {"teams": {"France": {"rating": 2000.0, "source": "live"}}}
        out = es.apply_expert_priors(ratings, sources=[])
        self.assertEqual(out["teams"]["France"]["rating"], 2000.0)
        self.assertEqual(out["teams"]["France"]["expert_delta"], 0.0)

    def test_folds_delta_into_rating_without_mutating_input(self):
        ratings = {"teams": {"France": {"rating": 2000.0, "source": "live"}}}
        src = _src({"France": {"lean": 2, "confidence": 1.0}})
        out = es.apply_expert_priors(ratings, sources=[src])
        self.assertEqual(out["teams"]["France"]["rating"], 2035.0)
        self.assertEqual(out["teams"]["France"]["expert_delta"], 35.0)
        # input untouched
        self.assertEqual(ratings["teams"]["France"]["rating"], 2000.0)
        self.assertNotIn("expert_delta", ratings["teams"]["France"])


class LoaderRobustness(unittest.TestCase):
    def test_missing_dir_returns_empty(self):
        self.assertEqual(es.load_sources(ROOT / "data" / "_nope_"), [])

    def test_real_wiloo_file_loads_and_is_safe(self):
        # The shipped Wiloo file must load and, while empty, move nothing.
        sources = es.load_sources()
        ratings = {"teams": {"France": {"rating": 2000.0, "source": "live"}}}
        out = es.apply_expert_priors(ratings, sources=sources)
        self.assertEqual(out["teams"]["France"]["rating"], 2000.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
