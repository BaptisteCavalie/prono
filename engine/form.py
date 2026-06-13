"""Derive the recent-form signal from completed fixtures.

Form is the model's *momentum* channel (see ``team_signals.FORM_WEIGHT``),
deliberately kept orthogonal to Elo. ``updater.apply_completed_results`` already
moves a team's rating by the *magnitude* of a result's surprise (goal margin and
opponent strength included), so form must NOT re-encode strength or the same
matches would be counted twice. Form therefore tracks the raw recent W/D/L
streak, recency-weighted, with only a light opponent tilt — never goal margin,
which Elo owns.

This is computed on demand by the results-update playbook (``/maj-resultats``),
not by the per-request autonomous refresh: form is a deliberate, persisted edit
to ``team_status.json``, scoped to the ``form`` field alone (injuries, news and
notes stay under the ask-Claude layer).
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Tuple

from engine import updater

# Last N completed matches that define "recent form".
FORM_WINDOW = 3
# Win/loss base before the opponent tilt — leaves headroom to reach ±1.0.
BASE = 0.7
# Rating gap (Elo points) that maps to the full opponent tilt, and its cap.
OPP_TILT_SCALE = 600.0
OPP_TILT_CAP = 0.3


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _team_rating(ratings: Dict, team: str) -> float:
    return float((ratings.get("teams", {}).get(team) or {}).get("rating", 0.0) or 0.0)


def _match_form_value(gf: int, ga: int, gap: float) -> float:
    """Per-match momentum in [-1, 1] from the team's point of view.

    ``gap`` is opponent_rating - team_rating: positive means a stronger
    opponent. A win over a stronger side tilts toward +1, a loss to a weaker
    side toward -1; a draw leans the same way but at half scale.
    """
    tilt = _clamp(gap / OPP_TILT_SCALE, -OPP_TILT_CAP, OPP_TILT_CAP)
    if gf > ga:                       # win: bonus for beating a stronger side
        return BASE + max(0.0, tilt)
    if gf < ga:                       # loss: malus for losing to a weaker side
        return -BASE - max(0.0, -tilt)
    return tilt * 0.5                 # draw: small credit vs stronger, debit vs weaker


def _team_completed_matches(team: str, fixtures: Iterable[Dict]) -> List[Dict]:
    played = []
    for m in fixtures:
        if m.get("home") != team and m.get("away") != team:
            continue
        if updater._as_int(m.get("actual_home")) is None or updater._as_int(m.get("actual_away")) is None:
            continue
        played.append(m)
    played.sort(key=updater._sort_key)
    return played


def compute_team_form(team: str, fixtures: Iterable[Dict], ratings: Dict) -> float:
    """Recency-weighted form in [-1, 1] from a team's completed matches.

    The most recent matches weigh the most (linear weights over the last
    ``FORM_WINDOW`` games). Returns ``0.0`` for a team that has not played yet.
    """
    played = _team_completed_matches(team, fixtures)[-FORM_WINDOW:]
    if not played:
        return 0.0
    team_rating = _team_rating(ratings, team)
    weighted_sum = 0.0
    weight_total = 0.0
    for i, m in enumerate(played, start=1):       # i = recency weight (1 = oldest in window)
        is_home = m.get("home") == team
        gf = updater._as_int(m.get("actual_home") if is_home else m.get("actual_away"))
        ga = updater._as_int(m.get("actual_away") if is_home else m.get("actual_home"))
        opponent = m.get("away") if is_home else m.get("home")
        gap = _team_rating(ratings, opponent) - team_rating
        weighted_sum += i * _match_form_value(gf, ga, gap)
        weight_total += i
    return round(_clamp(weighted_sum / weight_total, -1.0, 1.0), 2)


def recompute_form(team_status: Dict, fixtures: Iterable[Dict], ratings: Dict) -> Tuple[Dict, List[Tuple[str, float, float]]]:
    """Update ONLY the ``form`` field of every team that has completed matches.

    Injuries, suspensions, news risk and notes are left untouched — they belong
    to the ask-Claude layer. Returns the mutated status payload and the list of
    ``(team, old_form, new_form)`` actually changed, for reporting.
    """
    fixtures = list(fixtures)
    teams_with_results = sorted({
        t for m in fixtures
        if updater._as_int(m.get("actual_home")) is not None
        and updater._as_int(m.get("actual_away")) is not None
        for t in (m.get("home"), m.get("away")) if t
    })

    status_teams = team_status.setdefault("teams", {})
    changes: List[Tuple[str, float, float]] = []
    for team in teams_with_results:
        new_form = compute_team_form(team, fixtures, ratings)
        entry = status_teams.setdefault(team, {})
        old_form = round(float(entry.get("form", 0.0) or 0.0), 2)
        if old_form != new_form:
            entry["form"] = new_form
            changes.append((team, old_form, new_form))
    return team_status, changes
