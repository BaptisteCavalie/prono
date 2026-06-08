#!/usr/bin/env python3
"""WC2022 group stage, but combos use only A/B-rated picks (strong favourites).

Grade by the model's pick probability (same thresholds as engine/report.confidence,
where 'high' = >=55%):
    A  pick >= 65%      B  55-65%      C  45-55%      D  < 45%
Only A and B picks are eligible for combo tickets. Combos of size N=2..10 are
built from the A/B picks in schedule order, consecutive non-overlapping tickets;
a ticket wins iff all legs are correct.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import model  # noqa: E402
from tools.backtest_wc2022 import ELO_2022  # noqa: E402
from tools.backtest_wc2022_groupstage import GROUP_STAGE, HOST, HOST_ADV, outcome  # noqa: E402


def grade(p: float) -> str:
    if p >= 0.65:
        return "A"
    if p >= 0.55:
        return "B"
    if p >= 0.45:
        return "C"
    return "D"


def main() -> int:
    teams = {t: r for t, r in ELO_2022.items()}

    graded = []  # (grade, pick_label, prob, hit, scoreline_str)
    for md, grp, home, away, gh, ga in GROUP_STAGE:
        home_adv = HOST_ADV if home == HOST else 0.0
        out = model.analyse(teams[home], teams[away], home_adv=home_adv)
        probs = {"1": out["p_home"], "X": out["p_draw"], "2": out["p_away"]}
        pick = max(probs, key=probs.get)
        p = probs[pick]
        res = outcome(gh, ga)
        label = {"1": home, "X": "Draw", "2": away}[pick]
        graded.append((grade(p), label, p, pick == res,
                       f"{home} {gh}-{ga} {away}"))

    # Per-grade single accuracy
    print("PER-GRADE SINGLE-BET ACCURACY (all 48 games)")
    print("=" * 64)
    for g in ("A", "B", "C", "D"):
        rows = [r for r in graded if r[0] == g]
        if not rows:
            continue
        won = sum(r[3] for r in rows)
        print(f"  {g}: {won:>2}/{len(rows):<2} won  ({won/len(rows)*100:>3.0f}%)")
    print()

    # A/B eligible legs, in schedule order
    ab = [r for r in graded if r[0] in ("A", "B")]
    ab_hits = [r[3] for r in ab]
    won = sum(ab_hits)
    n = len(ab)
    print(f"A/B PICKS ONLY: {n} eligible legs, {won} correct ({won/n*100:.0f}%)")
    print("=" * 64)
    print("misses among A/B picks (these are what bust the combos):")
    for g, label, p, hit, score in ab:
        if not hit:
            print(f"  - {g} {label} {p*100:.0f}%   ->  {score}")
    print()

    print("COMBO BETS from A/B picks only (consecutive tickets)")
    print("=" * 64)
    print(f"{'legs':>5}{'tickets':>9}{'won':>6}{'lost':>6}{'win rate':>10}")
    print("-" * 64)
    for N in range(2, 11):
        full = n // N
        won_tickets = sum(1 for t in range(full) if all(ab_hits[t*N:(t+1)*N]))
        rem = n - full * N
        rate = (won_tickets / full * 100) if full else 0.0
        tail = f"   (+{rem} legs left over)" if rem else ""
        flag = "  — can't fill a ticket" if full == 0 else ""
        print(f"{N:>5}{full:>9}{won_tickets:>6}{full-won_tickets:>6}"
              f"{rate:>9.0f}%{tail}{flag}")
    print("-" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
