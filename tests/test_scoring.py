#!/usr/bin/env python3
"""Tests for the prono-accuracy classification used by the 'Justesse des pronos'
recap: exact / bon / erreur, plus the small-N aggregate.

Run: python3 tests/test_scoring.py   (or: python3 -m unittest)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import common


class TestClassifyProno(unittest.TestCase):
    def test_exact_score(self):
        self.assertEqual(common.classify_prono(2, 0, 2, 0), "exact")
        self.assertEqual(common.classify_prono(1, 1, 1, 1), "exact")

    def test_bon_resultat_right_outcome_wrong_score(self):
        # Prono 2-0 (victoire domicile), réel 2-1 (victoire domicile) -> bon.
        self.assertEqual(common.classify_prono(2, 0, 2, 1), "bon")
        # Nul prédit, autre nul réel.
        self.assertEqual(common.classify_prono(0, 0, 1, 1), "bon")
        # Victoire extérieur des deux côtés, scores différents.
        self.assertEqual(common.classify_prono(0, 2, 1, 3), "bon")

    def test_erreur_wrong_outcome(self):
        # Prono victoire domicile, réel victoire extérieur.
        self.assertEqual(common.classify_prono(2, 0, 0, 1), "erreur")
        # Prono nul, réel victoire domicile.
        self.assertEqual(common.classify_prono(1, 1, 2, 1), "erreur")
        # Prono victoire domicile, réel nul.
        self.assertEqual(common.classify_prono(2, 1, 1, 1), "erreur")

    def test_none_when_data_missing(self):
        self.assertIsNone(common.classify_prono(None, None, 2, 0))
        self.assertIsNone(common.classify_prono(2, 0, None, None))
        self.assertIsNone(common.classify_prono(2, None, 2, 0))

    def test_exact_on_draw(self):
        self.assertEqual(common.classify_prono(0, 0, 0, 0), "exact")

    def test_accepts_int_like_values(self):
        # fixtures.json peut stocker des entiers ; on tolère aussi les chaînes.
        self.assertEqual(common.classify_prono("2", "0", "2", "0"), "exact")

    def test_none_on_uncastable_present_value(self):
        # Une valeur présente mais non numérique (ex. "TBD") honore le contrat
        # « None si la donnée n'est pas exploitable », plutôt que de lever.
        self.assertIsNone(common.classify_prono(2, 0, "TBD", 0))


class TestTallyPronos(unittest.TestCase):
    def test_counts_and_total(self):
        verdicts = ["exact", "bon", "erreur", "bon", "exact"]
        counts = common.tally_pronos(verdicts)
        self.assertEqual(counts["exact"], 2)
        self.assertEqual(counts["bon"], 2)
        self.assertEqual(counts["erreur"], 1)
        self.assertEqual(counts["total"], 5)

    def test_ignores_none_and_unknown(self):
        counts = common.tally_pronos(["exact", None, "n/a", None])
        self.assertEqual(counts["exact"], 1)
        self.assertEqual(counts["total"], 1)

    def test_empty(self):
        counts = common.tally_pronos([])
        self.assertEqual(counts["total"], 0)
        self.assertEqual(counts["exact"], 0)

    def test_real_day1_state(self):
        # État réel du 12 juin 2026 : G01 Mexico 2-0 (prono 2-0) = exact,
        # G02 South Korea 2-1 (prono 2-0) = bon. Aucun erreur encore.
        verdicts = [
            common.classify_prono(2, 0, 2, 0),
            common.classify_prono(2, 0, 2, 1),
        ]
        counts = common.tally_pronos(verdicts)
        self.assertEqual((counts["exact"], counts["bon"], counts["erreur"]), (1, 1, 0))
        self.assertEqual(counts["total"], 2)


class TestPageRouting(unittest.TestCase):
    """Routage de la refonte dashboard : onglets legacy/inconnus → vue Matchs."""

    def _render(self, tab: str) -> str:
        import ui  # import local : pas d'effet réseau à l'import
        return ui._render_page([], None, tab=tab).decode("utf-8")

    def test_legacy_and_unknown_tabs_fall_back_to_matchs(self):
        for tab in ("futurs", "passes", "bogus", ""):
            self.assertIn("<h1>Matchs</h1>", self._render(tab), f"tab={tab!r}")

    def test_known_tabs_render_their_view(self):
        self.assertIn("<h1>Paris</h1>", self._render("paris"))
        self.assertIn("<h1>Diagnostics</h1>", self._render("diagnostics"))


if __name__ == "__main__":
    unittest.main()
