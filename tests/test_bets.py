#!/usr/bin/env python3
"""Tests for the real-bet settlement math behind the 'Suivi des paris' block:
net P&L per bet (gagne/perdu/rembourse), the cumulative tournament tally and
ROI. Money logic -> tested (constitution).

Run: python3 tests/test_bets.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import common


class TestBetNet(unittest.TestCase):
    def test_won_pays_profit_only(self):
        # Mise 10 @ 1.85 gagnée -> profit net 8.50 (pas 18.50 : la mise revient).
        self.assertAlmostEqual(common.bet_net({"stake": 10, "odds": 1.85, "status": "gagne"}), 8.5)

    def test_lost_loses_the_stake(self):
        self.assertAlmostEqual(common.bet_net({"stake": 10, "odds": 1.85, "status": "perdu"}), -10.0)

    def test_refund_is_zero(self):
        self.assertEqual(common.bet_net({"stake": 10, "odds": 1.85, "status": "rembourse"}), 0.0)

    def test_pending_has_no_pnl(self):
        self.assertIsNone(common.bet_net({"stake": 10, "odds": 1.85, "status": "en_cours"}))
        self.assertIsNone(common.bet_net({"stake": 10, "odds": 1.85}))  # défaut = en_cours

    def test_unusable_numbers_are_none(self):
        self.assertIsNone(common.bet_net({"stake": "x", "odds": 1.85, "status": "gagne"}))
        self.assertIsNone(common.bet_net({"stake": 10, "odds": 0.5, "status": "gagne"}))  # cote < 1
        self.assertIsNone(common.bet_net({"stake": -1, "odds": 2.0, "status": "perdu"}))


class TestBetStatus(unittest.TestCase):
    def test_normalises_and_defaults(self):
        self.assertEqual(common.bet_status({"status": "GAGNE"}), "gagne")
        self.assertEqual(common.bet_status({"status": " perdu "}), "perdu")
        self.assertEqual(common.bet_status({}), "en_cours")
        self.assertEqual(common.bet_status({"status": "n_importe_quoi"}), "en_cours")


class TestTallyBets(unittest.TestCase):
    def test_empty(self):
        agg = common.tally_bets([])
        self.assertEqual(agg["n_settled"], 0)
        self.assertEqual(agg["staked"], 0.0)
        self.assertEqual(agg["net"], 0.0)
        self.assertIsNone(agg["roi"])  # pas de division par zéro

    def test_mixed_slate(self):
        bets = [
            {"stake": 10, "odds": 1.85, "status": "gagne"},     # +8.50
            {"stake": 10, "odds": 3.00, "status": "perdu"},     # -10.00
            {"stake": 5, "odds": 2.00, "status": "rembourse"},  # 0.00
            {"stake": 20, "odds": 1.50, "status": "en_cours"},  # ignoré (pending)
        ]
        agg = common.tally_bets(bets)
        self.assertEqual(agg["n_settled"], 3)
        self.assertEqual(agg["n_won"], 1)
        self.assertEqual(agg["n_lost"], 1)
        self.assertEqual(agg["n_refunded"], 1)
        self.assertEqual(agg["n_pending"], 1)
        self.assertAlmostEqual(agg["staked"], 25.0)   # 10 + 10 + 5, le en_cours exclu
        self.assertAlmostEqual(agg["net"], -1.5)      # 8.50 - 10 + 0
        self.assertAlmostEqual(agg["roi"], -1.5 / 25.0)

    def test_negative_and_positive_roi_symmetric(self):
        # Le bilan ne privilégie aucun signe : un net négatif est un nombre normal.
        win = common.tally_bets([{"stake": 10, "odds": 2.0, "status": "gagne"}])
        self.assertAlmostEqual(win["roi"], 1.0)
        loss = common.tally_bets([{"stake": 10, "odds": 2.0, "status": "perdu"}])
        self.assertAlmostEqual(loss["roi"], -1.0)

    def test_settled_but_unusable_is_skipped_not_counted(self):
        bets = [
            {"stake": 10, "odds": 2.0, "status": "gagne"},   # +10
            {"stake": "?", "odds": 2.0, "status": "perdu"},  # inexploitable -> ignoré
        ]
        agg = common.tally_bets(bets)
        self.assertEqual(agg["n_settled"], 1)
        self.assertAlmostEqual(agg["staked"], 10.0)
        self.assertAlmostEqual(agg["net"], 10.0)


if __name__ == "__main__":
    unittest.main()
