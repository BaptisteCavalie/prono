"""Rating-driven Poisson match model. Pure stdlib (no numpy/scipy required).

Pipeline: rating difference -> win expectancy -> goal supremacy + a total that
grows with mismatch -> Poisson scoreline matrix -> Dixon-Coles low-score
correction (lifts draws, which independent Poisson underestimates) -> all the
match probabilities.

Constants are tuned for the FIFA-points rating scale in data/ratings.json and
are the knobs for recalibration.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

# --- Tunable parameters -----------------------------------------------------
BASE_TOTAL = 2.55           # baseline total goals for an evenly-matched game
MAX_SUPREMACY = 3.2         # cap on goal supremacy for a total mismatch
GOAL_MISMATCH_BOOST = 1.00  # extra total goals as the game gets more lopsided
RATING_DIVISOR = 400.0      # logistic scale for win expectancy (Elo scale)
RATING_SHRINK = 0.78        # damp the rating gap before it drives goals. The raw
                            # gap is overconfident: on the WC2022 group stage the
                            # favourite buckets the model priced ~72-88% only won
                            # ~43-71%, and its 1X2 logloss (1.20) was worse than a
                            # flat 33/33/33 coin (1.10). 0.78 removes the worst of
                            # that overconfidence without chasing that chaotic
                            # tournament's logloss optimum (~0.25 = overfit). Pick
                            # accuracy is unchanged (it never flips the favourite);
                            # only the *confidence* is pulled toward honesty.
DC_RHO = -0.13              # Dixon-Coles low-score correlation (negative lifts draws)
MIN_LAMBDA = 0.20           # floor on expected goals (no team is ever truly 0)
MAX_GOALS = 10              # scoreline grid size (Poisson tail beyond this ~ 0)

# Attack/defense profile (optional, off by default). The rating gap fixes *who*
# wins and the base total; these per-team multipliers let scoring tendency shape
# the *goal total* — the lever that drives Over/Under 2.5 and BTTS, which the
# rating-only model leaves to the BASE_TOTAL constant. This is the classic
# Poisson "attack strength × opponent defensive weakness" decomposition
# (Maher 1982; Dixon-Coles 1997), kept multiplicative and centred at 1.0 so a
# neutral profile reproduces the rating-only output exactly.
AVG_GOALS_PG = 1.35         # league-average goals-for per team per game (intl)
AD_CLAMP = (0.65, 1.55)     # bound attack/defense ratios against thin samples
NEUTRAL_AD = (1.0, 1.0)     # (attack, defense) for a team with no goals data


def win_expectancy(rating_diff: float) -> float:
    """Classic logistic expected score for the side with +rating_diff."""
    return 1.0 / (1.0 + 10 ** (-rating_diff / RATING_DIVISOR))


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def ad_from_row(row: Dict, league_avg: float = AVG_GOALS_PG) -> Tuple[float, float]:
    """(attack, defense) for a team's ratings row, or neutral if no goals data.

    Reads optional `goals_for_pg` / `goals_against_pg`. Missing/blank -> neutral,
    so the model is unchanged for any team without a scoring profile.
    """
    if not isinstance(row, dict):
        return NEUTRAL_AD
    gf = row.get("goals_for_pg")
    ga = row.get("goals_against_pg")
    if gf is None or ga is None:
        return NEUTRAL_AD
    try:
        return attack_defense_from_goals(float(gf), float(ga), league_avg)
    except (TypeError, ValueError):
        return NEUTRAL_AD


def attack_defense_from_goals(goals_for_pg: float, goals_against_pg: float,
                              league_avg: float = AVG_GOALS_PG) -> Tuple[float, float]:
    """Derive (attack, defense) multipliers from per-game goals scored/conceded.

    attack  > 1 -> scores more than an average side (raises its own lambda)
    defense > 1 -> concedes more than average / leakier (raises the opponent's
                   lambda). Both centred at 1.0 and clamped, so a side at the
                   league average is neutral. Feed rolling goals (or xG) over the
                   last ~6-12 matches; xG is the less noisy choice.
    """
    avg = league_avg if league_avg and league_avg > 0 else AVG_GOALS_PG
    attack = _clamp(float(goals_for_pg) / avg, *AD_CLAMP)
    defense = _clamp(float(goals_against_pg) / avg, *AD_CLAMP)
    return attack, defense


def expected_goals(rating_home: float, rating_away: float,
                   home_adv: float = 0.0,
                   ad_home: Tuple[float, float] = NEUTRAL_AD,
                   ad_away: Tuple[float, float] = NEUTRAL_AD) -> Tuple[float, float]:
    """Map two ratings to expected goals (lambda) for each side.

    The favourite's goals rise *and* the total rises with mismatch (blowouts
    are higher-scoring) — fixing the old "total stuck at ~2.7" behaviour.

    `ad_home`/`ad_away` are optional (attack, defense) multipliers; the defaults
    are neutral (1.0, 1.0), so omitting them leaves the rating-only behaviour
    byte-for-byte unchanged. When supplied, each side's lambda is scaled by its
    own attack and the opponent's defensive weakness.
    """
    dr = ((rating_home + home_adv) - rating_away) * RATING_SHRINK
    tilt = 2 * win_expectancy(dr) - 1                 # in [-1, 1]
    supremacy = MAX_SUPREMACY * tilt
    total = BASE_TOTAL + GOAL_MISMATCH_BOOST * abs(tilt)
    lam_home = (total + supremacy) / 2
    lam_away = (total - supremacy) / 2
    lam_home *= ad_home[0] * ad_away[1]
    lam_away *= ad_away[0] * ad_home[1]
    return max(MIN_LAMBDA, lam_home), max(MIN_LAMBDA, lam_away)


def poisson_pmf(k: int, lam: float) -> float:
    return lam ** k * math.exp(-lam) / math.factorial(k)


def _dc_tau(i: int, j: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles correction factor for the four low-score cells."""
    if i == 0 and j == 0:
        return 1.0 - lam * mu * rho
    if i == 0 and j == 1:
        return 1.0 + lam * rho
    if i == 1 and j == 0:
        return 1.0 + mu * rho
    if i == 1 and j == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lam_home: float, lam_away: float,
                 max_goals: int = MAX_GOALS, rho: float = DC_RHO) -> List[List[float]]:
    home = [poisson_pmf(i, lam_home) for i in range(max_goals + 1)]
    away = [poisson_pmf(j, lam_away) for j in range(max_goals + 1)]
    m = [[home[i] * away[j] for j in range(max_goals + 1)]
         for i in range(max_goals + 1)]
    for i, j in ((0, 0), (0, 1), (1, 0), (1, 1)):
        m[i][j] *= _dc_tau(i, j, lam_home, lam_away, rho)
    return m


def analyse(rating_home: float, rating_away: float, home_adv: float = 0.0,
            ad_home: Tuple[float, float] = NEUTRAL_AD,
            ad_away: Tuple[float, float] = NEUTRAL_AD) -> Dict:
    """Full model output for a single match.

    `ad_home`/`ad_away` are optional (attack, defense) multipliers; neutral by
    default so existing rating-only callers are unaffected.
    """
    lam_h, lam_a = expected_goals(rating_home, rating_away, home_adv,
                                  ad_home=ad_home, ad_away=ad_away)
    m = score_matrix(lam_h, lam_a)
    n = len(m)
    total = sum(m[i][j] for i in range(n) for j in range(n))  # renormalise (DC + tail)

    p_home = sum(m[i][j] for i in range(n) for j in range(n) if i > j) / total
    p_draw = sum(m[i][i] for i in range(n)) / total
    p_away = sum(m[i][j] for i in range(n) for j in range(n) if i < j) / total

    scorelines = sorted(
        (((i, j), m[i][j] / total) for i in range(n) for j in range(n)),
        key=lambda kv: kv[1], reverse=True,
    )
    p_over25 = sum(m[i][j] for i in range(n) for j in range(n)
                   if i + j >= 3) / total
    p_btts = sum(m[i][j] for i in range(1, n) for j in range(1, n)) / total

    return {
        "lambda_home": lam_h,
        "lambda_away": lam_a,
        "p_home": p_home,
        "p_draw": p_draw,
        "p_away": p_away,
        "top_scores": scorelines[:5],
        "p_over25": p_over25,
        "p_btts": p_btts,
    }


# --- Market helpers (used by the odds/value module) -------------------------
def implied_prob(decimal_odds: float) -> float:
    return 1.0 / decimal_odds if decimal_odds and decimal_odds > 1 else 0.0


def devig(odds: List[float]) -> List[float]:
    """Strip bookmaker margin from a set of decimal odds -> fair probs."""
    raw = [implied_prob(o) for o in odds]
    s = sum(raw)
    return [r / s for r in raw] if s else raw
