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

    def test_pending_exposure(self):
        # Exposition des paris en cours : mise totale engagée + gain total
        # possible (mise × cote, brut), distincts du bilan réglé.
        bets = [
            {"stake": 2, "odds": 1.82, "status": "en_cours"},   # misé 2, potentiel 3.64
            {"stake": 5, "odds": 1.50, "status": "en_cours"},   # misé 5, potentiel 7.50
            {"stake": 10, "odds": 2.0, "status": "gagne"},      # réglé -> hors expo en cours
        ]
        agg = common.tally_bets(bets)
        self.assertEqual(agg["n_pending"], 2)
        self.assertAlmostEqual(agg["staked_pending"], 7.0)
        self.assertAlmostEqual(agg["potential_pending"], 3.64 + 7.50)
        # le réglé ne pollue pas l'expo en cours
        self.assertAlmostEqual(agg["staked"], 10.0)

    def test_pending_unusable_numbers_skipped(self):
        agg = common.tally_bets([{"stake": "?", "odds": 1.5, "status": "en_cours"}])
        self.assertEqual(agg["n_pending"], 1)            # compté en effectif
        self.assertAlmostEqual(agg["staked_pending"], 0.0)   # mais pas en argent
        self.assertAlmostEqual(agg["potential_pending"], 0.0)

    def test_settled_but_unusable_is_skipped_not_counted(self):
        bets = [
            {"stake": 10, "odds": 2.0, "status": "gagne"},   # +10
            {"stake": "?", "odds": 2.0, "status": "perdu"},  # inexploitable -> ignoré
        ]
        agg = common.tally_bets(bets)
        self.assertEqual(agg["n_settled"], 1)
        self.assertAlmostEqual(agg["staked"], 10.0)
        self.assertAlmostEqual(agg["net"], 10.0)


class TestSettleStatus(unittest.TestCase):
    """Réglage auto depuis les résultats (tools/settle_bets.py)."""

    def _single(self, mid, pick):
        return {"status": "en_cours", "legs": [{"match": mid, "pick": pick}]}

    def test_leg_outcome(self):
        self.assertEqual(common.leg_outcome(2, 0), "home")
        self.assertEqual(common.leg_outcome(1, 1), "draw")
        self.assertEqual(common.leg_outcome(0, 3), "away")

    def test_single_win_loss_pending(self):
        res = {"G37": (2, 0)}
        self.assertEqual(common.settle_status(self._single("G37", "home"), res), "gagne")
        self.assertEqual(common.settle_status(self._single("G37", "draw"), res), "perdu")
        self.assertEqual(common.settle_status(self._single("G99", "home"), res), "en_cours")

    def test_combo_wins_only_when_all_legs_played_and_won(self):
        bet = {"status": "en_cours", "legs": [
            {"match": "G02", "pick": "home"}, {"match": "G24", "pick": "away"}]}
        # une jambe jouée+gagnée, l'autre pas encore -> en cours
        self.assertEqual(common.settle_status(bet, {"G02": (2, 1)}), "en_cours")
        # les deux jouées et gagnées -> gagné
        self.assertEqual(common.settle_status(bet, {"G02": (2, 1), "G24": (0, 1)}), "gagne")

    def test_combo_loses_the_instant_one_leg_loses_even_if_others_pending(self):
        bet = {"status": "en_cours", "legs": [
            {"match": "G02", "pick": "home"}, {"match": "G24", "pick": "away"}]}
        # G02 perdu (nul), G24 pas encore jouée -> perdu tout de suite
        self.assertEqual(common.settle_status(bet, {"G02": (1, 1)}), "perdu")

    def test_draw_pick_settles_correctly(self):
        bet = self._single("G21", "draw")
        self.assertEqual(common.settle_status(bet, {"G21": (1, 1)}), "gagne")
        self.assertEqual(common.settle_status(bet, {"G21": (2, 0)}), "perdu")

    def test_no_legs_keeps_status(self):
        # ancien format sans legs : on ne devine pas, statut inchangé
        self.assertEqual(common.settle_status({"status": "gagne"}, {"G01": (1, 0)}), "gagne")
        self.assertEqual(common.settle_status({"status": "en_cours"}, {}), "en_cours")

    def test_never_invents_a_refund(self):
        # rembourse n'est jamais produit automatiquement (cas void = manuel)
        bet = {"status": "en_cours", "legs": [{"match": "G37", "pick": "home"}]}
        self.assertIn(common.settle_status(bet, {"G37": (2, 0)}), ("gagne", "perdu", "en_cours"))


if __name__ == "__main__":
    unittest.main()
