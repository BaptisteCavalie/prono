#!/usr/bin/env python3
"""Garde-fous du verdict confiance/risque (ui._confidence_verdict).

Le verdict traduit la distribution 1N2 en décision de pari : sur quels favoris
NE PAS miser. C'est la vraie valeur de l'outil (la plupart des matchs ont un
favori net — le dire n'apporte rien ; pointer les favoris fragiles, si). Aide à
la décision -> testée.

Run: python3 -m unittest tests.test_confidence
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui


class ConfidenceVerdict(unittest.TestCase):
    def test_solid_favourite(self):
        v = ui._confidence_verdict(75, 18, 7)
        self.assertEqual(v["tier"], "solide")

    def test_coin_flip_is_open(self):
        # aucune issue >= 45 % -> pile ou face, à éviter
        v = ui._confidence_verdict(40, 33, 27)
        self.assertEqual(v["tier"], "ouvert")

    def test_draw_trap_flagged(self):
        # favori d'une équipe mais nul >= 30 % -> le piège classique
        v = ui._confidence_verdict(51, 30, 19)
        self.assertEqual(v["tier"], "piege")
        self.assertIn("nul", v["why"])

    def test_draw_as_top_pick_is_not_a_trap(self):
        # si le NUL est lui-même l'issue la plus probable, ce n'est pas un piège
        # « favori d'équipe » : ça tombe en serré/ouvert selon la concentration.
        v = ui._confidence_verdict(28, 45, 27)
        self.assertNotEqual(v["tier"], "piege")

    def test_thin_favourite_is_serre(self):
        # favori clair (>=45) mais ni solide ni piège -> serré
        v = ui._confidence_verdict(52, 23, 25)
        self.assertEqual(v["tier"], "serre")

    def test_strong_favourite_with_high_draw_is_trap_not_solid(self):
        # même un favori à 60 % bascule en piège si le nul est à 30 %+
        v = ui._confidence_verdict(60, 31, 9)
        self.assertEqual(v["tier"], "piege")

    def test_boundary_draw_exactly_30_is_trap(self):
        # frontière métier la plus litigieuse : nul à EXACTEMENT 30 (>=) sur un
        # favori d'équipe -> piège, même si le favori est par ailleurs solide.
        self.assertEqual(ui._confidence_verdict(60, 30, 10)["tier"], "piege")

    def test_boundary_top_45_vs_44(self):
        # top = 45 -> pas « ouvert » (45 n'est pas < 45) ; ici nul>=30 -> piège.
        self.assertEqual(ui._confidence_verdict(45, 33, 22)["tier"], "piege")
        # top = 44 -> bascule en « ouvert » (aucune issue ne se détache).
        self.assertEqual(ui._confidence_verdict(44, 33, 23)["tier"], "ouvert")

    def test_label_present_for_every_tier(self):
        for tier in ("solide", "serre", "piege", "ouvert"):
            self.assertIn(tier, ui._VERDICT_LABELS)


class PickVerdict(unittest.TestCase):
    """Le verdict de ligne porte la DÉCISION jouée (le pick MPP), pas le favori
    1N2 — sinon « Favori solide » + « prono 0-0 » + Nutri E se contredisent."""

    def test_pick_follows_favourite_is_confidence_tier(self):
        # pick == favori -> on retombe sur le tier de confiance 1N2
        v = ui._pick_verdict(75, 18, 7, "home")
        self.assertEqual(v["tier"], "solide")

    def test_short_favourite_draw_pick_says_play_draw(self):
        # favori (home) mais pick = nul -> « Jouer le nul »
        v = ui._pick_verdict(78, 15, 7, "draw")
        self.assertEqual(v["tier"], "nul")
        self.assertIn("nul", v["label"].lower())

    def test_underdog_value_pick_says_play_underdog(self):
        # favori (home) mais pick = outsider (away) -> « Jouer l'outsider »
        v = ui._pick_verdict(55, 25, 20, "away")
        self.assertEqual(v["tier"], "valeur")
        self.assertIn("outsider", v["label"].lower())

    def test_draw_favourite_drawn_pick_is_not_divergent(self):
        # si le NUL est lui-même le favori et qu'on joue le nul -> pas divergent
        v = ui._pick_verdict(28, 45, 27, "draw")
        self.assertNotIn(v["tier"], ("nul", "valeur"))


if __name__ == "__main__":
    unittest.main()
