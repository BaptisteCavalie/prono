#!/usr/bin/env python3
"""Full WC2022 group stage (48 games) backtest + a betting simulation.

- Single bets ("paris simples"): one bet per game on the model's 1X2 pick.
- Combo bets ("paris combines") of size N=2..10: the 48 chronological picks are
  split into consecutive non-overlapping tickets of N legs; a ticket wins only if
  ALL its legs are correct. Any trailing remainder (< N) is dropped and noted.

Picks use fixed pre-tournament Elo (no in-tournament updates) — i.e. what you'd
know on kickoff day. The composite "success score" is the repo metric
(engine/solidity), which applies its own in-run Elo updates.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import model, solidity  # noqa: E402
from tools.backtest_wc2022 import ELO_2022  # noqa: E402

HOST = "Qatar"
HOST_ADV = 65.0

# (matchday, group, home, away, goals_home, goals_away) — schedule order.
GROUP_STAGE = [
    # Matchday 1
    (1, "A", "Qatar", "Ecuador", 0, 2),
    (1, "A", "Senegal", "Netherlands", 0, 2),
    (1, "B", "England", "Iran", 6, 2),
    (1, "B", "USA", "Wales", 1, 1),
    (1, "C", "Argentina", "Saudi Arabia", 1, 2),
    (1, "C", "Mexico", "Poland", 0, 0),
    (1, "D", "Denmark", "Tunisia", 0, 0),
    (1, "D", "France", "Australia", 4, 1),
    (1, "E", "Germany", "Japan", 1, 2),
    (1, "E", "Spain", "Costa Rica", 7, 0),
    (1, "F", "Morocco", "Croatia", 0, 0),
    (1, "F", "Belgium", "Canada", 1, 0),
    (1, "G", "Switzerland", "Cameroon", 1, 0),
    (1, "G", "Brazil", "Serbia", 2, 0),
    (1, "H", "Uruguay", "South Korea", 0, 0),
    (1, "H", "Portugal", "Ghana", 3, 2),
    # Matchday 2
    (2, "A", "Qatar", "Senegal", 1, 3),
    (2, "A", "Netherlands", "Ecuador", 1, 1),
    (2, "B", "Wales", "Iran", 0, 2),
    (2, "B", "England", "USA", 0, 0),
    (2, "C", "Poland", "Saudi Arabia", 2, 0),
    (2, "C", "Argentina", "Mexico", 2, 0),
    (2, "D", "Tunisia", "Australia", 0, 1),
    (2, "D", "France", "Denmark", 2, 1),
    (2, "E", "Japan", "Costa Rica", 0, 1),
    (2, "E", "Spain", "Germany", 1, 1),
    (2, "F", "Belgium", "Morocco", 0, 2),
    (2, "F", "Croatia", "Canada", 4, 1),
    (2, "G", "Cameroon", "Serbia", 3, 3),
    (2, "G", "Brazil", "Switzerland", 1, 0),
    (2, "H", "South Korea", "Ghana", 2, 3),
    (2, "H", "Portugal", "Uruguay", 2, 0),
    # Matchday 3
    (3, "A", "Ecuador", "Senegal", 1, 2),
    (3, "A", "Netherlands", "Qatar", 2, 0),
    (3, "B", "Wales", "England", 0, 3),
    (3, "B", "Iran", "USA", 0, 1),
    (3, "C", "Poland", "Argentina", 0, 2),
    (3, "C", "Saudi Arabia", "Mexico", 1, 2),
    (3, "D", "Australia", "Denmark", 1, 0),
    (3, "D", "Tunisia", "France", 1, 0),
    (3, "E", "Japan", "Spain", 2, 1),
    (3, "E", "Costa Rica", "Germany", 2, 4),
    (3, "F", "Croatia", "Belgium", 0, 0),
    (3, "F", "Canada", "Morocco", 1, 2),
    (3, "G", "Serbia", "Switzerland", 2, 3),
    (3, "G", "Cameroon", "Brazil", 1, 0),
    (3, "H", "Ghana", "Uruguay", 0, 2),
    (3, "H", "South Korea", "Portugal", 2, 1),
]


def outcome(gh, ga):
    return "1" if gh > ga else ("2" if gh < ga else "X")


def build_fixtures():
    fx = []
    for i, (md, grp, home, away, gh, ga) in enumerate(GROUP_STAGE, start=1):
        fx.append({
            "id": f"WC22-{i:02d}", "matchday": md, "group": grp,
            "date": f"2022-11-{19 + md*3:02d}",  # rough order by matchday
            "home": home, "away": away,
            "actual_home": gh, "actual_away": ga,
            "home_adv": HOST_ADV if home == HOST else 0.0,
        })
    return fx


def main() -> int:
    ratings = {"teams": {t: {"rating": r} for t, r in ELO_2022.items()}}
    fx = build_fixtures()
    teams = ratings["teams"]

    hits = []          # bool per game, in schedule order
    upset_misses = []  # decisive games the model called wrong
    for m in fx:
        out = model.analyse(teams[m["home"]]["rating"], teams[m["away"]]["rating"],
                            home_adv=m["home_adv"])
        probs = {"1": out["p_home"], "X": out["p_draw"], "2": out["p_away"]}
        pick = max(probs, key=probs.get)
        res = outcome(m["actual_home"], m["actual_away"])
        ok = pick == res
        hits.append(ok)
        if not ok and res != "X":
            upset_misses.append(
                f"{m['home']} {m['actual_home']}-{m['actual_away']} {m['away']}")

    n = len(hits)
    won = sum(hits)
    draws = sum(1 for m in fx if m["actual_home"] == m["actual_away"])

    print("WC2022 FULL GROUP STAGE — 48 games")
    print("=" * 60)
    draw_losses = n - won - len(upset_misses)
    print(f"SINGLE BETS (paris simples): {won}/{n} won  ({won/n*100:.0f}%)")
    print(f"  (of the {n - won} losses: {len(upset_misses)} decisive upsets + "
          f"{draw_losses} draws the 1X2 model can't pick as favourite; "
          f"{draws} draws total)")
    print()

    print("COMBO BETS (paris combines) — picks split into consecutive tickets")
    print("=" * 60)
    print(f"{'legs':>5}{'tickets':>9}{'won':>6}{'lost':>6}{'win rate':>10}")
    print("-" * 60)
    for N in range(2, 11):
        full = n // N
        won_tickets = 0
        for t in range(full):
            chunk = hits[t * N:(t + 1) * N]
            if all(chunk):
                won_tickets += 1
        rem = n - full * N
        rate = (won_tickets / full * 100) if full else 0.0
        tail = f"   (+{rem} games left over, no ticket)" if rem else ""
        print(f"{N:>5}{full:>9}{won_tickets:>6}{full - won_tickets:>6}"
              f"{rate:>9.0f}%{tail}")
    print("-" * 60)

    print("\nWhy combos die: decisive games the model got WRONG (upsets):")
    for u in upset_misses:
        print(f"  - {u}")

    rep = solidity.assess_model_solidity(fx, ratings)
    print("\nSUCCESS SCORE (repo metric, engine/solidity)")
    print("=" * 60)
    print(f"  overall score   : {rep['score']}/100 ({rep['level']})")
    print(f"  1X2 accuracy    : {rep['result_accuracy']*100:.0f}%")
    print(f"  exact-score hit : {rep['exact_score_hit']*100:.0f}%")
    print(f"  Brier / log-loss: {rep['brier_1x2']:.3f} / {rep['logloss_1x2']:.3f}")
    print(f"  RPS (1X2)       : {rep['rps_1x2']:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
