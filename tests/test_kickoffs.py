#!/usr/bin/env python3
"""Guards for the Europe/Paris date/time fix (ui._apply_paris_kickoffs).

History: fixture dates were wrong on a deploy with no live odds feed — the
display fell back to stored dates that didn't account for US-evening kickoffs
rolling onto the next French day. The fix lets each fixture carry its own
committed ``kickoff_utc`` as a fallback when the feed has no entry.

Run: python3 -m unittest tests.test_kickoffs
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui
from engine import odds_fetch


class ParisKickoffs(unittest.TestCase):
    def setUp(self):
        # Deterministic: no live feed, so kickoff_utc is the only source.
        self._orig = odds_fetch.load_kickoffs
        odds_fetch.load_kickoffs = lambda: {}

    def tearDown(self):
        odds_fetch.load_kickoffs = self._orig

    def test_kickoff_utc_drives_paris_date_and_time(self):
        # 22:00Z = 00:00 Paris next day (CEST = UTC+2): the jetlag day rollover.
        fx = [{"id": "G13", "home": "Brazil", "away": "Morocco",
               "date": "2026-06-12", "kickoff_utc": "2026-06-13T22:00:00Z"}]
        ui._apply_paris_kickoffs(fx)
        self.assertEqual(fx[0]["date"], "2026-06-14")
        self.assertEqual(fx[0]["kickoff_paris"], "00:00")

    def test_no_kickoff_keeps_stored_date(self):
        fx = [{"id": "Z99", "home": "A", "away": "B", "date": "2026-06-12"}]
        ui._apply_paris_kickoffs(fx)
        self.assertEqual(fx[0]["date"], "2026-06-12")
        self.assertNotIn("kickoff_paris", fx[0])

    def test_live_feed_takes_precedence_over_kickoff_utc(self):
        odds_fetch.load_kickoffs = lambda: {"G13": "2026-06-14T17:00:00Z"}
        fx = [{"id": "G13", "home": "Brazil", "away": "Morocco",
               "date": "2026-06-12", "kickoff_utc": "2026-06-13T22:00:00Z"}]
        ui._apply_paris_kickoffs(fx)
        self.assertEqual(fx[0]["kickoff_paris"], "19:00")  # 17:00Z -> 19:00 Paris


if __name__ == "__main__":
    unittest.main(verbosity=2)
