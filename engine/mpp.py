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
    Timing/usage policy lives in engine/x2.py.

Why this beats the raw modal score: the model's single most likely scoreline is
very often 1-1, which throws away the 1N2 base points whenever the model actually
favours a winner. We instead (1) back the outcome that maximises P(outcome) x base
points, then (2) inside that outcome pick the score that maximises
P(exact) x rarity-bonus — so a contrarian 0-0 can beat a crowded 1-1 when the
model rates it nearly as likely. The crowd-share table is an estimate, so the
recommendation is always shown next to the model's raw top score for sanity.

Knockout matches: MPP scores the result AFTER extra time (penalties never
count), while the Poisson model describes 90 minutes. `recommend(knockout=True)`
therefore convolves every 90' draw with a short extra-time Poisson before
optimising, so a "1-1 then a goal in ET" world is priced as the 2-1 it ends as.

League-position modes (`mode=`): expected points is the right target only when
nothing separates you from the pack. A leader wants to cover the crowd's picks
(low variance), a trailing player wants the big-haul tail (high variance):
  * "ev"      — default: maximise expected MPP points.
  * "protect" — leader: most likely outcome + most likely exact score, no
                rarity chasing (you only need to not lose ground).
  * "chase"   — trailing: same outcome, but the exact score must carry a big
                bonus (>= tres rare) — maximise P(big haul), not E[points].
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

# --- Knockout (120-minute) adjustment ----------------------------------------
ET_FRACTION = 30.0 / 90.0   # extra time adds a third of regulation playing time
ET_TEMPO = 0.85             # per-minute scoring drops in ET (tired legs, caution)
MAX_ET_GOALS = 4            # Poisson tail beyond this in 30 minutes ~ 0

# --- League-position modes ----------------------------------------------------
MODES = ("ev", "protect", "chase")
CHASE_MIN_BONUS = 50        # chase mode only accepts >= "tres rare" scorelines
PROTECT_MAX_RANK = 3        # mode_for_position: top-N = protect the lead
CHASE_POINTS_BEHIND = 80    # mode_for_position: this far back = chase variance

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


def is_knockout(match: Optional[Dict]) -> bool:
    """True when a fixture is scored on the 120-minute result (MPP rule)."""
    return bool(match) and str(match.get("stage") or "group") != "group"


def knockout_distribution(out: Dict) -> Dict[Tuple[int, int], float]:
    """120' score distribution: every 90' draw is convolved with a 30' Poisson.

    Non-draw 90' scores are final (no extra time). A draw cell (i, i) spreads
    over (i+di, i+dj) with di/dj from a tempo-damped extra-time Poisson; the
    mass left on the diagonal is the "still level after 120', goes to pens"
    world, which MPP scores as a draw.
    """
    dist90 = score_distribution(out)
    lam_h = out["lambda_home"] * ET_FRACTION * ET_TEMPO
    lam_a = out["lambda_away"] * ET_FRACTION * ET_TEMPO
    et_h = [model.poisson_pmf(k, lam_h) for k in range(MAX_ET_GOALS + 1)]
    et_a = [model.poisson_pmf(k, lam_a) for k in range(MAX_ET_GOALS + 1)]
    sh, sa = sum(et_h) or 1.0, sum(et_a) or 1.0   # renormalise the cut tail
    et_h = [p / sh for p in et_h]
    et_a = [p / sa for p in et_a]

    dist120: Dict[Tuple[int, int], float] = {}
    for (i, j), p in dist90.items():
        if i != j:
            dist120[(i, j)] = dist120.get((i, j), 0.0) + p
            continue
        for di, ph in enumerate(et_h):
            for dj, pa in enumerate(et_a):
                key = (i + di, j + dj)
                dist120[key] = dist120.get(key, 0.0) + p * ph * pa
    return dist120


def mode_for_position(rank: Optional[int] = None, total: Optional[int] = None,
                      points_behind: Optional[float] = None) -> str:
    """Map a league position to a recommend() mode (leader/pack/trailing)."""
    if rank is not None and rank <= PROTECT_MAX_RANK:
        return "protect"
    if points_behind is not None and points_behind >= CHASE_POINTS_BEHIND:
        return "chase"
    if rank is not None and total and rank / total > 0.5:
        return "chase"
    return "ev"


def recommend(out: Dict, odds: Optional[List[float]] = None,
              knockout: bool = False, mode: str = "ev") -> Dict:
    """Recommend the MPP expected-points-optimal scoreline for one match.

    `odds` is an optional [home, draw, away] decimal triple. When present the
    favoured outcome maximises P(outcome) x base_points; otherwise it falls back
    to the model's most likely outcome.

    `knockout=True` optimises on the 120-minute distribution (MPP counts extra
    time, never penalties). `mode` is one of MODES — see the module docstring.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if knockout:
        dist = knockout_distribution(out)
        p_out = {o: sum(p for s, p in dist.items() if outcome_of(*s) == o)
                 for o in ("home", "draw", "away")}
    else:
        dist = score_distribution(out)
        p_out = {"home": out["p_home"], "draw": out["p_draw"], "away": out["p_away"]}

    base = None
    if odds and len(odds) == 3:
        base = {
            "home": base_points(odds[0]),
            "draw": base_points(odds[1]),
            "away": base_points(odds[2]),
        }

    if mode == "protect":
        # Protecting a lead: cover the field's most likely pick, ignore cotes.
        out_pick = max(p_out, key=lambda o: p_out[o])
    elif base and all(v is not None for v in base.values()):
        out_pick = max(p_out, key=lambda o: p_out[o] * base[o])
    else:
        out_pick = max(p_out, key=lambda o: p_out[o])

    in_outcome = [(s, p) for s, p in dist.items() if outcome_of(*s) == out_pick]
    cands = [(s, p) for s, p in in_outcome if p >= MIN_SCORE_PROB]
    if not cands:  # outcome is so unlikely nothing clears the floor — take its best
        cands = [max(in_outcome, key=lambda sp: sp[1])]

    if mode == "protect":
        score, p_exact = max(cands, key=lambda sp: sp[1])
    elif mode == "chase":
        # Big-haul hunting: only scorelines with a serious bonus, lower floor.
        chase = [(s, p) for s, p in in_outcome
                 if bonus_for_score(s) >= CHASE_MIN_BONUS and p >= MIN_SCORE_PROB / 2]
        score, p_exact = max(chase or cands,
                             key=lambda sp: sp[1] * bonus_for_score(sp[0]))
    else:
        score, p_exact = max(cands, key=lambda sp: sp[1] * bonus_for_score(sp[0]))

    bonus = bonus_for_score(score)
    base_pts = base[out_pick] if base else None
    exp_base = (p_out[out_pick] * base_pts) if base_pts is not None else None
    exp_bonus = p_exact * bonus
    exp_points = (exp_base or 0.0) + exp_bonus

    modal = out["top_scores"][0][0]
    return {
        "score": score,                 # (home, away) recommended scoreline
        "outcome": out_pick,            # "home" / "draw" / "away"
        "knockout": knockout,           # True = optimised on the 120' distribution
        "mode": mode,                   # "ev" / "protect" / "chase"
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
