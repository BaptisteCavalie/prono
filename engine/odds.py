"""Compare model probabilities to market odds -> de-vigged fair prices + value.

This is the sound core of any "copy/value" strategy: a bet has value only when
the model's probability beats the *fair* (margin-removed) market probability and
the offered odds give positive expected value.
"""
from typing import Dict, List

from engine import calibration, model

EDGE_THRESHOLD = 0.03   # model prob must beat fair prob by >=3 pts to flag value


def value_1x2(out: Dict, odds_home: float, odds_draw: float,
              odds_away: float) -> List[Dict]:
    fair = model.devig([odds_home, odds_draw, odds_away])
    # Compare the *calibrated* model probability to the price: the raw model is
    # overconfident on big favourites, which manufactured fake "value" on short
    # odds (cf. the -20% ROI on manually-placed favourite bets). Calibration pulls
    # that confidence toward honesty before any edge is claimed (engine/calibration.py).
    model_p = list(calibration.calibrated_1x2(out))
    decs = [odds_home, odds_draw, odds_away]
    rows = []
    for sel, mp, fp, dec in zip(("home", "draw", "away"), model_p, fair, decs):
        ev = mp * dec - 1.0                      # expected value per unit staked
        edge = mp - fp
        rows.append({
            "sel": sel, "model": mp, "fair": fp, "odds": dec,
            "edge": edge, "ev": ev,
            "value": edge >= EDGE_THRESHOLD and ev > 0,
        })
    return rows
