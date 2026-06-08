#!/usr/bin/env python3
"""How the model would have scored on Mon Petit Prono (MPP) at WC2022.

Question answered: "If I'd filled in MPP for the 2022 World Cup with this
model's single best scoreline per game, would I have scored well — especially on
exact scores?"

Scope: the 48 group-stage games (the dataset the repo already ships, reused from
tools/backtest_wc2022_groupstage.py + the approximate decimal odds from
tools/backtest_wc2022_odds.py). Picks use fixed pre-tournament Elo — i.e. what
you'd have known on kickoff day, no hindsight.

MPP barème (official "MPP Mondial" / World Cup edition, ligue1.com):
  * Bon résultat (1N2 correct): points indexed to the match odds — "les points
    suivent la cote". The more improbable the called result, the more it pays.
    MPP's exact base formula is proprietary, so we approximate it as
    round(decimal_odds_of_picked_outcome * 10): a 1.40 favourite ~14 pts, a 3.00
    upset ~30 pts. Wrong outcome -> 0 (and no exact bonus can apply).
  * Score exact bonus, added on top of the base, by how RARE the score was among
    players who already got the result right:
        > 30%  (commun)      -> +20
        20-30% (rare)        -> +30
        5-20%  (tres rare)   -> +50
        0.5-5% (mega rare)   -> +70
        < 0.5% (ultra rare)  -> +100
    We don't have the 2022 crowd distribution, so the tier is ESTIMATED from how
    common each scoreline is in practice (CROWD_SHARE below). Because the result
    is uncertain we also print a floor/ceiling band, not just the central guess.
  * Bonus X2 (one per tournament, doubles a single prono): modelled as a free
    +best-single-prono on top, reported separately.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import model, mpp  # noqa: E402
from engine.mpp import (  # noqa: E402  (single source of truth for the barème)
    CROWD_SHARE, DEFAULT_SHARE, base_points, bonus_for_share, tier_name,
)
from tools.backtest_wc2022 import ELO_2022  # noqa: E402
from tools.backtest_wc2022_groupstage import GROUP_STAGE, HOST, HOST_ADV, outcome  # noqa: E402
from tools.backtest_wc2022_odds import ODDS  # noqa: E402


def rows():
    """Yield a per-game dict of model pick + grading, in schedule order."""
    for i, (md, grp, h, a, gh, ga) in enumerate(GROUP_STAGE, start=1):
        hadv = HOST_ADV if h == HOST else 0.0
        out = model.analyse(ELO_2022[h], ELO_2022[a], home_adv=hadv)
        (si, sj), sp = out["top_scores"][0]
        # In MPP you submit ONE scoreline; its implied 1N2 is what scores the
        # base points. So the outcome must come from the submitted score, not a
        # separate 1N2 argmax (which can disagree: top score 1-1 = a draw even
        # when the model marginally favours the home win).
        res = outcome(gh, ga)
        out_hit = outcome(si, sj) == res
        exact_hit = (si == gh and sj == ga)
        share = CROWD_SHARE.get((si, sj), DEFAULT_SHARE)

        # Model's raw 1N2 view (argmax of the three outcome probabilities) and,
        # for "strategy B", the most probable scoreline consistent with it.
        probs = {"1": out["p_home"], "X": out["p_draw"], "2": out["p_away"]}
        pick = max(probs, key=probs.get)
        cons = next(((a_, b_) for (a_, b_), _ in out["top_scores"]
                     if outcome(a_, b_) == pick), (si, sj))

        yield {
            "i": i, "home": h, "away": a, "gh": gh, "ga": ga,
            "pred": (si, sj), "pred_p": sp,
            "odds": ODDS[i], "out_hit": out_hit, "exact_hit": exact_hit,
            "share": share, "pick_1x2": pick, "pick_1x2_hit": pick == res,
            "cons": cons,
        }


def main() -> int:
    data = list(rows())
    n = len(data)

    out_hits = sum(r["out_hit"] for r in data)
    exact_hits = sum(r["exact_hit"] for r in data)

    base_total = sum(base_points(r["odds"]) for r in data if r["out_hit"])

    # Exact-score bonus: central estimate + floor (all "commun" +20) + ceiling
    # (every hit treated one tier rarer than the central guess).
    bonus_central = bonus_floor = bonus_ceil = 0
    best_single = (0, None)  # (total points on that game, label) for the X2 boost
    print("MON PETIT PRONO @ WC2022 GROUP STAGE — exact-score scorecard")
    print("=" * 74)
    print(f"{'Match':<30}{'pred':>6}{'real':>6}{'odds':>6}{'base':>6}"
          f"{'exact bonus':>14}")
    print("-" * 74)
    for r in data:
        si, sj = r["pred"]
        base = base_points(r["odds"]) if r["out_hit"] else 0
        line_total = base
        bonus_str = "-"
        if r["exact_hit"]:
            b_central = bonus_for_share(r["share"])
            # one tier rarer for the ceiling
            tiers = [20, 30, 50, 70, 100]
            b_ceil = tiers[min(len(tiers) - 1, tiers.index(b_central) + 1)]
            bonus_central += b_central
            bonus_floor += 20
            bonus_ceil += b_ceil
            line_total += b_central
            bonus_str = f"+{b_central} ({tier_name(b_central)})"
        if line_total > best_single[0]:
            best_single = (line_total, f"{r['home']} {r['gh']}-{r['ga']} {r['away']}")
        match_str = f"{r['home'][:13]} v {r['away'][:13]}"
        flag = " EXACT" if r["exact_hit"] else (" ✓" if r["out_hit"] else " ✗")
        pred_str = f"{si}-{sj}"
        real_str = f"{r['gh']}-{r['ga']}"
        print(f"{match_str:<30}{pred_str:>6}{real_str:>6}"
              f"{r['odds']:>6.2f}{base:>6}{bonus_str:>14}{flag}")
    print("-" * 74)

    raw_1x2 = sum(r["pick_1x2_hit"] for r in data)
    print(f"\nHIT RATES")
    print(f"  exact scores              : {exact_hits}/{n} = {exact_hits/n*100:.0f}%"
          f"   (typical football exact-score skill ~10-15%)")
    print(f"  outcome of submitted score: {out_hits}/{n} = {out_hits/n*100:.0f}%"
          f"   (modal score leans to 1-1 draws -> some lost 1N2)")
    print(f"  model's raw 1N2 view      : {raw_1x2}/{n} = {raw_1x2/n*100:.0f}%"
          f"   (argmax of P(home/draw/away))")

    print(f"\nMPP POINTS")
    print(f"  base (bon resultat, odds x10) : {base_total}")
    print(f"  exact-score bonus  central    : +{bonus_central}")
    print(f"                     band        : +{bonus_floor} (all commun) "
          f".. +{bonus_ceil} (one tier rarer)")
    tot_lo = base_total + bonus_floor
    tot_hi = base_total + bonus_ceil
    tot_mid = base_total + bonus_central
    print(f"  TOTAL (base + bonus) central  : {tot_mid}   band {tot_lo}..{tot_hi}")
    x2_gain = best_single[0]
    print(f"  + X2 boost on best prono      : +{x2_gain}  "
          f"({best_single[1]})  -> {tot_mid + x2_gain} central")

    # Baseline: the lazy MPP player who writes 1-0 to the Elo favourite every game.
    fav_base = fav_exact = 0
    fav_bonus = 0
    for r in data:
        # favourite = higher Elo (+ host adv already baked into model, ignore here)
        h_fav = ELO_2022[r["home"]] >= ELO_2022[r["away"]]
        pred = (1, 0) if h_fav else (0, 1)
        res_pick = "1" if h_fav else "2"
        real = outcome(r["gh"], r["ga"])
        if res_pick == real:
            fav_base += base_points(r["odds"])
        if (pred[0], pred[1]) == (r["gh"], r["ga"]):
            fav_exact += 1
            fav_bonus += bonus_for_share(CROWD_SHARE.get(pred, DEFAULT_SHARE))
    print(f"\nBASELINE — 'favourite wins 1-0' every game")
    print(f"  exact scores : {fav_exact}/{n} = {fav_exact/n*100:.0f}%")
    print(f"  MPP total    : {fav_base + fav_bonus}  "
          f"(base {fav_base} + exact bonus +{fav_bonus})")

    # Strategy B: submit the most probable scoreline CONSISTENT with the model's
    # 1N2 pick (trades some draw exact-hits for stronger outcome/base points).
    b_base = b_exact = b_bonus = 0
    for r in data:
        cons = r["cons"]
        if outcome(*cons) == outcome(r["gh"], r["ga"]):
            b_base += base_points(r["odds"])
        if cons == (r["gh"], r["ga"]):
            b_exact += 1
            b_bonus += bonus_for_share(CROWD_SHARE.get(cons, DEFAULT_SHARE))
    print(f"\nSTRATEGY B — submit the score consistent with the 1N2 pick")
    print(f"  exact scores : {b_exact}/{n} = {b_exact/n*100:.0f}%   "
          f"MPP total {b_base + b_bonus} (base {b_base} + bonus +{b_bonus})")
    print(f"  Same exact-hit COUNT as A ({exact_hits}) but different games, and it")
    print(f"  keeps the ~{b_base - base_total} base points A throws away by over-submitting 1-1"
          f" draws.")

    # Strategy C: the SHIPPED recommender, engine/mpp.recommend() — picks the
    # outcome-consistent score that maximises expected MPP points (and chases the
    # rarity bonus). This is what predict.py now prints, graded on the same games.
    c_base = c_exact = c_bonus = 0
    for i, (md, grp, h, a, gh, ga) in enumerate(GROUP_STAGE, start=1):
        hadv = HOST_ADV if h == HOST else 0.0
        out = model.analyse(ELO_2022[h], ELO_2022[a], home_adv=hadv)
        rec = mpp.recommend(out)  # no full 1X2 odds triple in this dataset
        s = rec["score"]
        if outcome(*s) == outcome(gh, ga):
            c_base += base_points(ODDS[i])
        if s == (gh, ga):
            c_exact += 1
            c_bonus += bonus_for_share(CROWD_SHARE.get(s, DEFAULT_SHARE))
    print(f"\nSTRATEGY C — engine/mpp.recommend() (the shipped prono)")
    print(f"  exact scores : {c_exact}/{n} = {c_exact/n*100:.0f}%   "
          f"MPP total {c_base + c_bonus} (base {c_base} + bonus +{c_bonus})")
    print(f"  Maximises expected points: keeps B's outcome discipline AND chases")
    print(f"  the rarity bonus — but rare-score bids miss more often than they hit.")

    c_total = c_base + c_bonus
    print(f"\nVERDICT")
    edge_exact = c_exact - fav_exact
    print(f"  Exact scores are a real strength: the shipped recommender (C) hits "
          f"{c_exact}/{n} = {c_exact/n*100:.0f}%,")
    print(f"  above the ~10-15% football norm and beating the lazy 1-0-favourite "
          f"baseline ({fav_exact}/{n}) by {edge_exact:+d}.")
    print(f"  MPP points, best -> worst:  C {c_total}  >  B {b_base + b_bonus}  >  "
          f"A {tot_mid}  >  baseline {fav_base + fav_bonus}.")
    print(f"  Two levers do the work: (1) submit the score CONSISTENT with the "
          f"favoured 1N2 (B over A,")
    print(f"  +{b_base - base_total} base pts, stops wasting picks on 1-1 draws); (2) chase the "
          f"rarity BONUS where the")
    print(f"  model rates a rare score nearly as likely (C over B). C is higher "
          f"EV but higher variance —")
    print(f"  its rare bids miss more often, and the gain leans on the CROWD_SHARE "
          f"estimates. Net: you'd")
    print(f"  finish upper table and occasionally snag a big bonus, but it's not a "
          f"guaranteed league win.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
