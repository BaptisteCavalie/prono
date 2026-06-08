#!/usr/bin/env python3
"""Quick backtest of the model on the 2022 World Cup group-stage *first round*
(matchday 1 = the first 16 games, one per team-pair, played 20-24 Nov 2022).

It reuses the live scoring code (engine/solidity.assess_model_solidity) so the
"success score" is exactly the metric the repo reports for WC2026 — no special
casing. Inputs that the repo doesn't ship for 2022:

  * Ratings: pre-tournament World Football Elo (eloratings.net snapshot,
    ~20 Nov 2022). Approximate but on the correct Elo scale; Belgium ~2006 (5th)
    confirmed from public sources and used to anchor the top end.
  * Fixtures + final scores: the 16 matchday-1 results (well documented).

Notes on fairness:
  * Pure rating-only mode (no goals_for/against profiles), so the model is judged
    on what it actually knew before kickoff, not on hindsight scoring data.
  * Qatar were hosts -> the opener Qatar vs Ecuador carries the same +65 Elo host
    advantage the model applies for WC2026 hosts. Every other group game neutral.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import solidity  # noqa: E402

# Pre-WC2022 World Football Elo (eloratings.net, ~20 Nov 2022). Approximate.
ELO_2022 = {
    "Brazil": 2169,
    "Argentina": 2143,
    "Spain": 2048,
    "Netherlands": 2040,
    "Belgium": 2006,
    "Portugal": 2005,
    "France": 2003,
    "Denmark": 1965,
    "Germany": 1958,
    "Uruguay": 1935,
    "England": 1929,
    "Croatia": 1907,
    "Switzerland": 1899,
    "Serbia": 1885,
    "Ecuador": 1831,
    "Morocco": 1820,
    "Japan": 1816,
    "Poland": 1813,
    "Mexico": 1810,
    "USA": 1801,
    "Iran": 1796,
    "Wales": 1791,
    "Senegal": 1763,
    "Costa Rica": 1743,
    "South Korea": 1736,
    "Australia": 1714,
    "Canada": 1707,
    "Qatar": 1685,
    "Tunisia": 1678,
    "Saudi Arabia": 1632,
    "Cameroon": 1623,
    "Ghana": 1562,
}

# Group-stage matchday 1 (home, away, goals_home, goals_away).
MD1 = [
    ("Qatar", "Ecuador", 0, 2),
    ("England", "Iran", 6, 2),
    ("Senegal", "Netherlands", 0, 2),
    ("USA", "Wales", 1, 1),
    ("Argentina", "Saudi Arabia", 1, 2),
    ("Denmark", "Tunisia", 0, 0),
    ("Mexico", "Poland", 0, 0),
    ("France", "Australia", 4, 1),
    ("Morocco", "Croatia", 0, 0),
    ("Germany", "Japan", 1, 2),
    ("Spain", "Costa Rica", 7, 0),
    ("Belgium", "Canada", 1, 0),
    ("Switzerland", "Cameroon", 1, 0),
    ("Uruguay", "South Korea", 0, 0),
    ("Portugal", "Ghana", 3, 2),
    ("Brazil", "Serbia", 2, 0),
]

HOST = "Qatar"
HOST_ADV = 65.0  # same conservative host bump the model uses for WC2026 hosts


def build_ratings() -> dict:
    return {"teams": {t: {"rating": r} for t, r in ELO_2022.items()}}


def build_fixtures() -> list:
    fixtures = []
    for i, (home, away, gh, ga) in enumerate(MD1, start=1):
        home_adv = HOST_ADV if home == HOST else 0.0
        fixtures.append({
            "id": f"WC22-{i:02d}",
            "date": "2022-11-2%d" % (i % 10),  # rough, only used for sort order
            "matchday": 1,
            "home": home,
            "away": away,
            "actual_home": gh,
            "actual_away": ga,
            "home_adv": home_adv,
        })
    return fixtures


def outcome(gh, ga):
    return "1" if gh > ga else ("2" if gh < ga else "X")


def main() -> int:
    from engine import model

    ratings = build_ratings()
    fixtures = build_fixtures()

    print("WC2022 GROUP STAGE — ROUND 1 (matchday 1, 16 games)")
    print("=" * 72)
    print(f"{'Match':<34}{'model pick':>13}{'result':>9}{'hit':>5}")
    print("-" * 72)

    teams = ratings["teams"]
    hits = 0
    for m in fixtures:
        rh = teams[m["home"]]["rating"]
        ra = teams[m["away"]]["rating"]
        out = model.analyse(rh, ra, home_adv=m["home_adv"])
        probs = {"1": out["p_home"], "X": out["p_draw"], "2": out["p_away"]}
        pick = max(probs, key=probs.get)
        gh, ga = m["actual_home"], m["actual_away"]
        res = outcome(gh, ga)
        ok = pick == res
        hits += ok
        (si, sj), sp = out["top_scores"][0]
        label = {"1": m["home"], "X": "Draw", "2": m["away"]}[pick]
        match_str = f"{m['home']} vs {m['away']}"
        print(f"{match_str:<34}{label[:9]+' '+format(probs[pick]*100,'.0f')+'%':>13}"
              f"{str(gh)+'-'+str(ga):>9}{('  ✓' if ok else '  ✗'):>5}")

    print("-" * 72)
    print(f"1X2 picks correct: {hits}/{len(fixtures)} = {hits/len(fixtures)*100:.0f}%\n")

    rep = solidity.assess_model_solidity(fixtures, ratings)
    print("SUCCESS SCORE (repo metric: engine/solidity.assess_model_solidity)")
    print("=" * 72)
    print(f"  overall score      : {rep['score']}/100  ({rep['level']})")
    print(f"  1X2 accuracy       : {rep['result_accuracy']*100:.0f}%")
    print(f"  exact-score hit    : {rep['exact_score_hit']*100:.0f}%")
    print(f"  Brier (1X2)        : {rep['brier_1x2']:.3f}   (lower better)")
    print(f"  log-loss (1X2)     : {rep['logloss_1x2']:.3f}   (lower better)")
    print(f"  RPS (1X2)          : {rep['rps_1x2']:.3f}   (lower better)")
    print(f"  avg pick confidence: {rep['avg_pick_conf']*100:.0f}%")
    print(f"  calibration gap    : {rep['calibration_gap']*100:+.1f}pt (conf - hit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
