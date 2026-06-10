"""Mon Petit Prono (MPP) scoring — turn the model's score matrix into the
scoreline that maximises *expected MPP points*, not just the single most likely
score.

MPP barème ("MPP Mondial" / World Cup edition):
  * Bon resultat (1N2 correct): points indexed to the match odds — "les points
    suivent la cote". MPP's exact base formula is proprietary; we approximate it
    as round(decimal_odds_of_the_picked_outcome * 10). Wrong outcome -> 0, and no
    exact bonus can apply.
  * Score exact bonus, added on top, by how RARE the score is among players who
    already got the result right:
        > 30%  (commun)      -> +20
        20-30% (rare)        -> +30
        5-20%  (tres rare)   -> +50
        0.5-5% (mega rare)   -> +70
        < 0.5% (ultra rare)  -> +100
  * Bonus X2 (one per tournament): doubles every point of a single prono.

Why this beats the raw modal score: the model's single most likely scoreline is
very often 1-1, which throws away the 1N2 base points whenever the model actually
favours a winner. We instead (1) back the outcome that maximises P(outcome) x base
points, then (2) inside that outcome pick the score that maximises
P(exact) x rarity-bonus — so a contrarian 0-0 can beat a crowded 1-1 when the
model rates it nearly as likely. The crowd-share table is an estimate, so the
recommendation is always shown next to the model's raw top score for sanity.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine import model

# (max crowd share, bonus points) — first tier whose threshold the share meets.
BONUS_TIERS: List[Tuple[float, int]] = [
    (0.30, 20),   # commun
    (0.20, 30),   # rare        (20-30%)
    (0.05, 50),   # tres rare   (5-20%)
    (0.005, 70),  # mega rare   (0.5-5%)
    (0.0, 100),   # ultra rare  (<0.5%)
]

# Estimated share of correct-result players who submit a given exact score.
# Common scores get piled on (small bonus); odd scores are rare (big bonus).
CROWD_SHARE: Dict[Tuple[int, int], float] = {
    (1, 0): 0.28, (0, 1): 0.28,
    (2, 1): 0.20, (1, 2): 0.20,
    (1, 1): 0.24,
    (2, 0): 0.16, (0, 2): 0.16,
    (0, 0): 0.12,
    (3, 1): 0.07, (1, 3): 0.07,
    (3, 0): 0.06, (0, 3): 0.06,
    (2, 2): 0.05,
    (4, 0): 0.05, (0, 4): 0.05,    # an "expected blowout" pick, not truly rare
    (4, 1): 0.035, (1, 4): 0.035,
    (3, 2): 0.025, (2, 3): 0.025,
    (5, 0): 0.012, (0, 5): 0.012,
    (3, 3): 0.012,
}
DEFAULT_SHARE = 0.01  # any score not listed counts as a rare scoreline

# Ignore freak scorelines the model barely believes in when optimising the bonus.
MIN_SCORE_PROB = 0.03

_TIER_NAME = {20: "commun", 30: "rare", 50: "tres rare",
              70: "mega rare", 100: "ultra rare"}


def bonus_for_share(share: float) -> int:
    for max_share, pts in BONUS_TIERS:
        if share >= max_share:
            return pts
    return 100


def bonus_for_score(score: Tuple[int, int]) -> int:
    return bonus_for_share(CROWD_SHARE.get(score, DEFAULT_SHARE))


def tier_name(pts: int) -> str:
    return _TIER_NAME.get(pts, "?")


def base_points(odds: Optional[float]) -> Optional[int]:
    """MPP base ('bon resultat') points, approximated as odds x 10."""
    if odds is None or odds <= 1:
        return None
    return round(odds * 10)


def outcome_of(i: int, j: int) -> str:
    if i > j:
        return "home"
    if i < j:
        return "away"
    return "draw"


def score_distribution(out: Dict) -> Dict[Tuple[int, int], float]:
    """Full normalised P(exact score) grid, rebuilt from the model's lambdas."""
    lam_h = out["lambda_home"]
    lam_a = out["lambda_away"]
    m = model.score_matrix(lam_h, lam_a)
    n = len(m)
    total = sum(m[i][j] for i in range(n) for j in range(n)) or 1.0
    return {(i, j): m[i][j] / total for i in range(n) for j in range(n)}


def recommend(out: Dict, odds: Optional[List[float]] = None) -> Dict:
    """Recommend the MPP expected-points-optimal scoreline for one match.

    `odds` is an optional [home, draw, away] decimal triple. When present the
    favoured outcome maximises P(outcome) x base_points; otherwise it falls back
    to the model's most likely outcome.
    """
    dist = score_distribution(out)
    p_out = {"home": out["p_home"], "draw": out["p_draw"], "away": out["p_away"]}

    base = None
    if odds and len(odds) == 3:
        base = {
            "home": base_points(odds[0]),
            "draw": base_points(odds[1]),
            "away": base_points(odds[2]),
        }

    if base and all(v is not None for v in base.values()):
        out_pick = max(p_out, key=lambda o: p_out[o] * base[o])
    else:
        out_pick = max(p_out, key=lambda o: p_out[o])

    # Inside the chosen outcome, maximise P(exact) x rarity-bonus.
    cands = [(s, p) for s, p in dist.items()
             if outcome_of(*s) == out_pick and p >= MIN_SCORE_PROB]
    if not cands:  # outcome is so unlikely nothing clears the floor — take its best
        cands = [max(((s, p) for s, p in dist.items() if outcome_of(*s) == out_pick),
                     key=lambda sp: sp[1])]
    score, p_exact = max(
        cands, key=lambda sp: sp[1] * bonus_for_score(sp[0]))

    bonus = bonus_for_score(score)
    base_pts = base[out_pick] if base else None
    exp_base = (p_out[out_pick] * base_pts) if base_pts is not None else None
    exp_bonus = p_exact * bonus
    exp_points = (exp_base or 0.0) + exp_bonus

    modal = out["top_scores"][0][0]
    return {
        "score": score,                 # (home, away) recommended scoreline
        "outcome": out_pick,            # "home" / "draw" / "away"
        "p_exact": p_exact,             # model P(this exact score)
        "p_outcome": p_out[out_pick],   # model P(this outcome)
        "bonus": bonus,                 # exact-score bonus points if it lands
        "tier": tier_name(bonus),       # rarity tier label
        "base_points": base_pts,        # base points if outcome lands (needs odds)
        "exp_base": exp_base,           # expected base points
        "exp_bonus": exp_bonus,         # expected exact-score bonus
        "exp_points": exp_points,       # total expected MPP points
        "modal_score": modal,           # model's raw most-likely score
        "differs": tuple(score) != tuple(modal),
    }


def line(rec: Dict) -> str:
    """One-line human summary of a recommendation."""
    i, j = rec["score"]
    base_str = (f", base ~{rec['base_points']}" if rec["base_points"] is not None
                else "")
    tail = "" if not rec["differs"] else f"  (model top {rec['modal_score'][0]}-{rec['modal_score'][1]})"
    return (f"{i}-{j}  P(exact) {round(rec['p_exact'] * 100)}%  "
            f"bonus +{rec['bonus']} ({rec['tier']}){base_str}  "
            f"E[MPP] {rec['exp_points']:.1f}{tail}")
