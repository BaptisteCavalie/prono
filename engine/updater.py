"""Apply completed fixture results to team ratings before new predictions.

This keeps daily predictions reactive: as soon as actual scores are recorded in
fixtures.json, ratings are re-estimated locally on the next CLI run.
"""
from __future__ import annotations

import copy
import math
from typing import Dict, Iterable, Tuple

from engine import model

K_FACTOR = 24.0


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sort_key(match: Dict) -> Tuple:
    date_value = match.get("date")
    date_key = str(date_value) if date_value else "9999-99-99"
    return (date_key, match.get("matchday", 99), match.get("id", ""))


def _goal_mult(goal_diff: int, rating_diff: float) -> float:
    # Elo-style multiplier that gives more weight to convincing wins.
    return math.log(abs(goal_diff) + 1.0) * (2.2 / (abs(rating_diff) * 0.001 + 2.2))


def apply_completed_results(ratings: Dict, fixtures: Iterable[Dict]) -> Tuple[Dict, int]:
    """Return a copy of ratings adjusted with completed fixture outcomes.

    A fixture is considered completed when both actual_home and actual_away are
    present and parseable as integers.
    """
    out = copy.deepcopy(ratings)
    teams = out.get("teams", {})
    applied = 0

    for m in sorted(fixtures, key=_sort_key):
        home = m.get("home")
        away = m.get("away")
        if home not in teams or away not in teams:
            continue

        gh = _as_int(m.get("actual_home"))
        ga = _as_int(m.get("actual_away"))
        if gh is None or ga is None:
            continue

        rh = float(teams[home]["rating"])
        ra = float(teams[away]["rating"])
        home_adv = float(m.get("home_adv", 0.0) or 0.0)

        expected_home = model.win_expectancy((rh + home_adv) - ra)
        expected_away = 1.0 - expected_home

        if gh > ga:
            actual_home, actual_away = 1.0, 0.0
        elif gh < ga:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home, actual_away = 0.5, 0.5

        mult = _goal_mult(gh - ga, (rh + home_adv) - ra)
        delta = K_FACTOR * mult

        teams[home]["rating"] = round(rh + delta * (actual_home - expected_home), 2)
        teams[away]["rating"] = round(ra + delta * (actual_away - expected_away), 2)
        applied += 1

    return out, applied
