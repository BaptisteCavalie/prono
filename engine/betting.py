"""Safe staking strategy: turn model probabilities + market odds into a sized
betting plan. Pure stdlib.

Designed around what the WC2022 backtest actually showed (see tools/backtest_wc2022*):
  * Backing favourites because they're favourites loses money — only bet measured
    *value* (model prob > de-vigged market prob AND positive EV).
  * The model is OVERCONFIDENT (A-grade picks won ~57% vs ~75% implied). So before
    sizing we SHRINK the model's probability toward the market's fair probability.
    This is the single most important safety lever: it shrinks fake edges created
    by overconfidence and therefore shrinks stakes on them.
  * Combos compound the bookmaker margin and variance. In the backtest every combo
    of >=4 legs returned -100%. So combos are capped at 2 legs, tiny flat stake,
    drawn from a small ring-fenced sub-bankroll, and only built from independent
    value legs.

Staking is fractional Kelly on the *shrunk* edge, hard-capped per bet, with a
slate-level exposure cap. The defaults are deliberately conservative ("safe").
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine import model

# --- Tunable safety knobs ---------------------------------------------------
MARKET_WEIGHT = 0.50        # blend model<-market: shrunk = (1-w)*model + w*fair
MIN_EDGE = 0.04             # require >=4pt edge on the SHRUNK prob to bet
MAX_PLAUSIBLE_EDGE = 0.15   # raw model edge above this = likely model error, skip
KELLY_FRACTION = 0.25       # quarter-Kelly (smoother than full Kelly)
MAX_STAKE_FRAC = 0.02       # hard cap: 2% of bankroll on any single
SLATE_EXPOSURE_CAP = 0.15   # total live single-bet stake per slate
MIN_ODDS = 1.30             # skip very short prices: no room for value, big downside

COMBO_MAX_LEGS = 2          # never stack more than this
COMBO_BANKROLL_FRAC = 0.05  # combos may only use this share of bankroll, total
COMBO_STAKE_FRAC = 0.005    # flat 0.5% of bankroll per combo ticket

SELECTIONS = ("home", "draw", "away")


def shrink_probs(model_p: List[float], fair_p: List[float],
                 market_weight: float = MARKET_WEIGHT) -> List[float]:
    """Blend model probs toward de-vigged market probs, then renormalise.

    market_weight=0 -> trust the model fully; 1 -> just copy the market. The
    backtest's overconfidence is why the default leans halfway to the market.
    """
    w = max(0.0, min(1.0, market_weight))
    blended = [(1 - w) * m + w * f for m, f in zip(model_p, fair_p)]
    s = sum(blended)
    return [b / s for b in blended] if s else blended


def kelly_fraction(p: float, dec: float) -> float:
    """Full-Kelly stake fraction for prob p at decimal odds dec (0 if no edge)."""
    if dec <= 1.0:
        return 0.0
    f = (p * dec - 1.0) / (dec - 1.0)
    return max(0.0, f)


def evaluate_single(out: Dict, odds_triple: Tuple[float, float, float],
                    market_weight: float = MARKET_WEIGHT,
                    kelly_fraction_mult: float = KELLY_FRACTION) -> Optional[Dict]:
    """Best safe single bet for one match, or None if nothing qualifies.

    Returns the recommended selection with shrunk prob, edge, EV and a stake
    expressed as a *fraction of bankroll* (caller multiplies by bankroll).
    """
    odds_home, odds_draw, odds_away = odds_triple
    fair = model.devig([odds_home, odds_draw, odds_away])
    model_p = [out["p_home"], out["p_draw"], out["p_away"]]
    shrunk = shrink_probs(model_p, fair, market_weight)
    decs = [odds_home, odds_draw, odds_away]

    candidates = []
    for sel, mp, sp, fp, dec in zip(SELECTIONS, model_p, shrunk, fair, decs):
        if dec < MIN_ODDS:
            continue
        raw_edge = mp - fp
        if raw_edge > MAX_PLAUSIBLE_EDGE:      # too-good-to-be-true => model error
            continue
        edge = sp - fp                          # edge on the conservative prob
        ev = sp * dec - 1.0
        if edge < MIN_EDGE or ev <= 0:
            continue
        stake = min(MAX_STAKE_FRAC, kelly_fraction_mult * kelly_fraction(sp, dec))
        if stake <= 0:
            continue
        candidates.append({
            "sel": sel, "odds": dec, "model": mp, "shrunk": sp, "fair": fp,
            "edge": edge, "ev": ev, "stake_frac": stake,
        })
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["ev"])


def plan_singles(evaluations: List[Dict], bankroll: float) -> List[Dict]:
    """Apply the slate exposure cap across a set of single-bet evaluations.

    Each item: {"key", "label", "bet"} where bet is an evaluate_single result.
    Scales every stake down proportionally if the slate cap would be breached.
    """
    bets = [e for e in evaluations if e.get("bet")]
    total_frac = sum(e["bet"]["stake_frac"] for e in bets)
    scale = min(1.0, SLATE_EXPOSURE_CAP / total_frac) if total_frac else 1.0
    out = []
    for e in bets:
        b = e["bet"]
        out.append({
            **e,
            "stake": round(b["stake_frac"] * scale * bankroll, 2),
        })
    return out


def build_combos(staked_singles: List[Dict], bankroll: float) -> List[Dict]:
    """Conservative 2-leg combos from independent value singles.

    Pairs the highest-EV value singles (best with second-best, etc.), each leg
    using the shrunk prob so the combo must clear the margin on conservative
    numbers. Tiny flat stake, total combo outlay capped at COMBO_BANKROLL_FRAC.
    """
    legs = sorted(staked_singles, key=lambda e: e["bet"]["ev"], reverse=True)
    combos = []
    budget = COMBO_BANKROLL_FRAC * bankroll
    spent = 0.0
    stake = COMBO_STAKE_FRAC * bankroll
    for i in range(0, len(legs) - 1, COMBO_MAX_LEGS):
        chunk = legs[i:i + COMBO_MAX_LEGS]
        if len(chunk) < 2:
            break
        dec = 1.0
        p = 1.0
        for leg in chunk:
            dec *= leg["bet"]["odds"]
            p *= leg["bet"]["shrunk"]
        ev = p * dec - 1.0
        if ev <= 0:                      # combo doesn't survive the margin -> skip
            continue
        if spent + stake > budget:
            break
        spent += stake
        combos.append({
            "legs": [{"label": leg["label"], "sel": leg["bet"]["sel"],
                      "odds": leg["bet"]["odds"], "match_id": leg.get("match_id", "")}
                     for leg in chunk],
            "combined_odds": round(dec, 2),
            "combined_prob": p,
            "ev": ev,
            "stake": round(stake, 2),
        })
    return combos
