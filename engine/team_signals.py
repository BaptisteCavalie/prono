"""Team status signals: injuries/suspensions/form/news -> rating adjustment."""
from __future__ import annotations

import copy
from typing import Dict, Iterable

FORM_WEIGHT = 28.0
INJURY_WEIGHT = 36.0
SUSPENSION_WEIGHT = 24.0
NEWS_RISK_WEIGHT = 12.0


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _entry_delta(entry: Dict) -> float:
    form = _clamp(float(entry.get("form", 0.0) or 0.0), -1.0, 1.0)
    injury = _clamp(float(entry.get("injury_impact", 0.0) or 0.0), 0.0, 1.0)
    suspension = _clamp(float(entry.get("suspension_impact", 0.0) or 0.0), 0.0, 1.0)
    news = _clamp(float(entry.get("news_risk", 0.0) or 0.0), 0.0, 1.0)
    return (form * FORM_WEIGHT) - (injury * INJURY_WEIGHT) - (suspension * SUSPENSION_WEIGHT) - (news * NEWS_RISK_WEIGHT)


def adjusted_rating(base_rating: float, entry: Dict) -> float:
    return round(float(base_rating) + _entry_delta(entry), 2)


def adjust_ratings_with_status(ratings: Dict, team_status: Dict) -> Dict:
    out = copy.deepcopy(ratings)
    teams = out.get("teams", {})
    status_map = (team_status or {}).get("teams", {})
    for team, row in teams.items():
        entry = status_map.get(team, {})
        base = float(row.get("rating", 0.0))
        row["baseline_rating"] = base
        row["status_delta"] = round(_entry_delta(entry), 2)
        row["rating"] = adjusted_rating(base, entry)
    return out


def status_notes(team: str, team_status: Dict) -> Iterable[str]:
    entry = (team_status or {}).get("teams", {}).get(team, {})
    notes = entry.get("notes", [])
    if isinstance(notes, list):
        return [str(n) for n in notes if n]
    return []
