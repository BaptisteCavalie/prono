#!/usr/bin/env python3
"""P&L of the WC2022 group-stage bets at (approximate) real market odds.

ODDS are approximate decimal closing odds for the MODEL'S PICKED selection in
each of the 48 games, in schedule order (see GROUP_STAGE). They reflect the real
price ranges at the time (favourites short: Argentina ~1.16, Brazil ~1.40, etc.)
but are estimates, not an exact bookmaker feed — good enough to show the sign and
rough size of the P&L. Stake = 1 unit per ticket throughout.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import model  # noqa: E402
from tools.backtest_wc2022 import ELO_2022  # noqa: E402
from tools.backtest_wc2022_groupstage import GROUP_STAGE, HOST, HOST_ADV, outcome  # noqa: E402
from tools.backtest_wc2022_ab import grade  # noqa: E402

# Approximate decimal odds of the model's picked selection, by schedule index 1..48.
ODDS = {
    1: 2.40, 2: 1.80, 3: 1.40, 4: 2.05, 5: 1.16, 6: 2.75, 7: 1.40, 8: 1.33,
    9: 1.42, 10: 1.30, 11: 2.10, 12: 1.40, 13: 1.70, 14: 1.40, 15: 1.70, 16: 1.30,
    17: 1.55, 18: 1.70, 19: 3.00, 20: 1.65, 21: 1.95, 22: 1.55, 23: 2.80, 24: 2.05,
    25: 1.70, 26: 2.30, 27: 1.55, 28: 1.70, 29: 1.85, 30: 1.55, 31: 1.85, 32: 2.30,
    33: 2.10, 34: 1.20, 35: 1.70, 36: 2.20, 37: 1.55, 38: 1.85, 39: 1.85, 40: 1.65,
    41: 1.70, 42: 1.50, 43: 2.40, 44: 2.00, 45: 2.70, 46: 1.45, 47: 1.65, 48: 1.85,
}


def legs():
    """Yield (idx, grade, hit, odds) for each game in schedule order."""
    teams = ELO_2022
    for i, (md, grp, home, away, gh, ga) in enumerate(GROUP_STAGE, start=1):
        home_adv = HOST_ADV if home == HOST else 0.0
        out = model.analyse(teams[home], teams[away], home_adv=home_adv)
        probs = {"1": out["p_home"], "X": out["p_draw"], "2": out["p_away"]}
        pick = max(probs, key=probs.get)
        hit = pick == outcome(gh, ga)
        yield i, grade(probs[pick]), hit, ODDS[i]


def pnl_singles(rows, title):
    n = len(rows)
    staked = float(n)
    ret = sum(o for _, _, hit, o in rows if hit)
    won = sum(1 for _, _, hit, _ in rows if hit)
    print(f"{title}: {won}/{n} won | staked {staked:.0f} | "
          f"returned {ret:.2f} | net {ret - staked:+.2f} | "
          f"ROI {(ret - staked) / staked * 100:+.0f}%")


def pnl_combos(rows, title):
    hits = [hit for _, _, hit, _ in rows]
    odds = [o for _, _, _, o in rows]
    n = len(rows)
    print(f"\n{title} (consecutive tickets, 1u each)")
    print("-" * 64)
    print(f"{'legs':>4}{'tix':>5}{'won':>5}{'staked':>9}{'returned':>11}"
          f"{'net':>10}{'ROI':>8}")
    tot_stake = tot_ret = 0.0
    for N in range(2, 11):
        full = n // N
        staked = float(full)
        ret = 0.0
        won = 0
        for t in range(full):
            sl = slice(t * N, (t + 1) * N)
            if all(hits[sl]):
                won += 1
                prod = 1.0
                for o in odds[sl]:
                    prod *= o
                ret += prod
        tot_stake += staked
        tot_ret += ret
        roi = ((ret - staked) / staked * 100) if staked else 0.0
        print(f"{N:>4}{full:>5}{won:>5}{staked:>9.0f}{ret:>11.2f}"
              f"{ret - staked:>+10.2f}{roi:>+7.0f}%")
    print("-" * 64)
    print(f"{'all':>4}{'':>5}{'':>5}{tot_stake:>9.0f}{tot_ret:>11.2f}"
          f"{tot_ret - tot_stake:>+10.2f}"
          f"{(tot_ret - tot_stake) / tot_stake * 100:>+7.0f}%")


def main() -> int:
    rows = list(legs())
    ab = [r for r in rows if r[1] in ("A", "B")]

    print("SINGLE BETS at approx market odds (1u each)")
    print("=" * 64)
    pnl_singles(rows, "  all 48 picks")
    pnl_singles(ab, "  A/B picks only")

    pnl_combos(ab, "A/B COMBOS at approx market odds")

    # Show the combos that actually cashed (sizes 2 and 3 only had winners)
    hits = [h for _, _, h, _ in ab]
    odds = [o for _, _, _, o in ab]
    print("\nWinning A/B combo tickets:")
    for N in (2, 3):
        for t in range(len(ab) // N):
            sl = slice(t * N, (t + 1) * N)
            if all(hits[sl]):
                prod = 1.0
                for o in odds[sl]:
                    prod *= o
                print(f"  {N}-leg ticket #{t+1}: odds "
                      f"{' x '.join(f'{o:.2f}' for o in odds[sl])} = {prod:.2f} "
                      f"-> +{prod - 1:.2f}u")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
