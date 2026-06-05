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
DC_RHO = -0.13              # Dixon-Coles low-score correlation (negative lifts draws)
MIN_LAMBDA = 0.20           # floor on expected goals (no team is ever truly 0)
MAX_GOALS = 10              # scoreline grid size (Poisson tail beyond this ~ 0)


def win_expectancy(rating_diff: float) -> float:
    """Classic logistic expected score for the side with +rating_diff."""
    return 1.0 / (1.0 + 10 ** (-rating_diff / RATING_DIVISOR))


def expected_goals(rating_home: float, rating_away: float,
                   home_adv: float = 0.0) -> Tuple[float, float]:
    """Map two ratings to expected goals (lambda) for each side.

    The favourite's goals rise *and* the total rises with mismatch (blowouts
    are higher-scoring) — fixing the old "total stuck at ~2.7" behaviour.
    """
    dr = (rating_home + home_adv) - rating_away
    tilt = 2 * win_expectancy(dr) - 1                 # in [-1, 1]
    supremacy = MAX_SUPREMACY * tilt
    total = BASE_TOTAL + GOAL_MISMATCH_BOOST * abs(tilt)
    lam_home = max(MIN_LAMBDA, (total + supremacy) / 2)
    lam_away = max(MIN_LAMBDA, (total - supremacy) / 2)
    return lam_home, lam_away


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


def analyse(rating_home: float, rating_away: float, home_adv: float = 0.0) -> Dict:
    """Full model output for a single match."""
    lam_h, lam_a = expected_goals(rating_home, rating_away, home_adv)
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
