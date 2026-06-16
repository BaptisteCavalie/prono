#!/usr/bin/env python3
"""Bilan de calibration 1N2 — juge le modèle sur ses PROBABILITÉS, pas sur le
score sec affiché.

Pourquoi : le prono affiché est un seul score (le plus probable). Un score de
nul n'est presque jamais le score modal (la masse « nul » est éparpillée sur
0-0/1-1/2-2…), donc chaque nul réel est compté « erreur » même quand le modèle
lui donnait 25-30 %. Le récap exact/bon/erreur sous-estime donc structurellement
un modèle probabiliste. Cet outil mesure la vraie qualité du forecast.

Méthode : pour chaque match TERMINÉ, on reconstruit la proba d'avant-match en
repartant de la baseline Elo figée (data/ratings.json) + UNIQUEMENT les résultats
antérieurs au match (jamais le sien), + les priors experts statiques. On exclut
volontairement l'overlay « forme » (team_status.json reflète des résultats
postérieurs → fuite) : la mesure est donc plutôt CONSERVATRICE (elle prive le
modèle d'un signal qu'il avait). Si le modèle est bon même comme ça, c'est
crédible.

Scores propres (plus c'est bas, mieux c'est) :
- Brier multiclasse : Σ(p_k − y_k)²  — baseline tirage uniforme = 0.667
- RPS (ordinal H<N<A) : le score de référence du forecast foot — uniforme ≈ 0.25
- Log-loss : −log p(issue réelle) — uniforme = 1.099
On compare aussi le taux où l'ISSUE la plus probable du modèle tombe, au taux du
score sec (le récap actuel), pour chiffrer la pénalité « nul ».

Run :  python3 tools/calibration.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "data" / "fixtures.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import data, expert_signals, prediction, updater


def _sort_key(m):
    return (str(m.get("date") or "9999-99-99"), m.get("matchday", 99), m.get("id", ""))


def _outcome_index(home_goals: int, away_goals: int) -> int:
    """0 = victoire domicile, 1 = nul, 2 = victoire extérieur."""
    if home_goals > away_goals:
        return 0
    if home_goals < away_goals:
        return 2
    return 1


def ratings_as_of(target, fixtures):
    """Ratings reconstruits tels qu'AVANT le coup d'envoi de ``target`` :
    baseline figée + seuls les résultats des matchs antérieurs (ordre
    chronologique), + priors experts. Le match cible et tous les suivants ont
    leur score masqué — aucune fuite du résultat à mesurer."""
    tkey = _sort_key(target)
    as_of = []
    for m in fixtures:
        mm = dict(m)
        if _sort_key(m) >= tkey:            # le match lui-même et les suivants : score caché
            mm["actual_home"] = None
            mm["actual_away"] = None
        as_of.append(mm)
    r = data.load_ratings()                 # baseline figée (relue à neuf à chaque appel)
    r, _ = updater.apply_completed_results(r, as_of)
    r = expert_signals.apply_expert_priors(r)
    return r


def main(argv=None) -> int:
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures = json.load(f).get("matches", [])

    done = sorted(
        [m for m in fixtures
         if m.get("actual_home") is not None and m.get("actual_away") is not None],
        key=_sort_key,
    )
    if not done:
        print("Aucun match terminé : rien à mesurer.")
        return 0

    rows = []
    for m in done:
        out = prediction.analyse_match(m, ratings_as_of(m, fixtures))
        if not out:
            continue
        p = [float(out["p_home"]), float(out["p_draw"]), float(out["p_away"])]
        s = sum(p) or 1.0
        p = [x / s for x in p]               # normalise (sécurité)
        actual = _outcome_index(int(m["actual_home"]), int(m["actual_away"]))
        rows.append((m, p, actual))

    n = len(rows)
    labels = ("V dom.", "Nul", "V ext.")

    def brier(p, a):
        return sum((p[k] - (1.0 if k == a else 0.0)) ** 2 for k in range(3))

    def rps(p, a):
        # ordinal H<N<A : moyenne des carrés d'écart de CDF sur les 2 seuils
        cp = [p[0], p[0] + p[1]]
        ca = [1.0 if a <= 0 else 0.0, 1.0 if a <= 1 else 0.0]
        return sum((cp[i] - ca[i]) ** 2 for i in range(2)) / 2.0

    def logloss(p, a):
        return -math.log(max(p[a], 1e-12))

    model_brier = sum(brier(p, a) for _, p, a in rows) / n
    model_rps = sum(rps(p, a) for _, p, a in rows) / n
    model_ll = sum(logloss(p, a) for _, p, a in rows) / n
    argmax_hits = sum(1 for _, p, a in rows if max(range(3), key=lambda k: p[k]) == a)

    # Baseline tirage uniforme (33/33/33)
    uni = [1 / 3, 1 / 3, 1 / 3]
    uni_brier = sum(brier(uni, a) for _, _, a in rows) / n
    uni_rps = sum(rps(uni, a) for _, _, a in rows) / n
    uni_ll = sum(logloss(uni, a) for _, _, a in rows) / n

    # Récap actuel (score sec) : bon 1N2 = issue du score figé == issue réelle
    score_hits = 0
    for m, _, a in rows:
        ph, pa = m.get("predicted_home"), m.get("predicted_away")
        if ph is not None and pa is not None:
            score_hits += int(_outcome_index(int(ph), int(pa)) == a)

    print(f"=== Calibration 1N2 — {n} matchs terminés ===")
    print("(probas reconstruites : Elo as-of + priors experts, hors overlay forme — indicatif)\n")
    print(f"  Issue la + probable du modèle tombe : {argmax_hits}/{n} = {100*argmax_hits/n:.0f}%")
    print(f"  Issue du SCORE SEC affiché tombe     : {score_hits}/{n} = {100*score_hits/n:.0f}%"
          f"   <- le récap actuel")
    print(f"    -> écart = pénalité « nul » du score sec\n")
    print("  Scores propres (bas = bon)      modèle   |  uniforme 33/33/33")
    print(f"    Brier (0-2)                 {model_brier:7.3f}  |  {uni_brier:7.3f}"
          f"   {'OK' if model_brier < uni_brier else 'PIRE'}")
    print(f"    RPS  (0-1, réf. foot)       {model_rps:7.3f}  |  {uni_rps:7.3f}"
          f"   {'OK' if model_rps < uni_rps else 'PIRE'}")
    print(f"    Log-loss                    {model_ll:7.3f}  |  {uni_ll:7.3f}"
          f"   {'OK' if model_ll < uni_ll else 'PIRE'}")

    # Combien de proba le modèle mettait-il sur l'issue réelle, en moyenne ?
    avg_p_actual = sum(p[a] for _, p, a in rows) / n
    draws = [(m, p) for m, p, a in rows if a == 1]
    print(f"\n  Proba moyenne donnée à l'issue réellement tombée : {100*avg_p_actual:.0f}%")
    if draws:
        avg_pdraw = sum(p[1] for _, p in draws) / len(draws)
        print(f"  Sur les {len(draws)} nuls réels : proba moyenne de nul donnée = {100*avg_pdraw:.0f}% "
              f"(jamais le score modal)")

    print("\n=== Détail match par match ===")
    print("  match                         V dom.  Nul  V ext.  | réel")
    for m, p, a in rows:
        star = "  <-- issue réelle"
        print(f"  {m['id']} {m['home'][:12]:12}-{m['away'][:12]:12} "
              f"{100*p[0]:4.0f}% {100*p[1]:4.0f}% {100*p[2]:4.0f}%  | {labels[a]}{star}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
