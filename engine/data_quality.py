"""Data freshness and quality checks for fixtures/ratings/team status."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Iterable, List


def _parse_date_ymd(value: str):
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _parse_iso(value: str):
    if not value:
        return None
    raw = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return _parse_date_ymd(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def assess_data_health(fixtures: Iterable[Dict], ratings: Dict, team_status: Dict,
                       now: datetime | None = None) -> Dict:
    now = now or datetime.now(timezone.utc)
    alerts: List[str] = []
    score = 100

    fixtures = list(fixtures)
    if not fixtures:
        return {
            "score": 0,
            "level": "critical",
            "alerts": ["Aucun fixture charge"],
            "fixtures_missing_dates": 0,
            "fixtures_past_without_score": 0,
            "ratings_age_days": None,
            "status_age_days": None,
        }

    missing_dates = sum(1 for m in fixtures if not m.get("date"))
    if missing_dates:
        score -= min(20, missing_dates)
        alerts.append(f"{missing_dates} match(s) sans date")

    past_without_score = 0
    for m in fixtures:
        d = _parse_date_ymd(m.get("date")) if m.get("date") else None
        if not d:
            continue
        if d.date() < now.date():
            if m.get("actual_home") is None or m.get("actual_away") is None:
                past_without_score += 1
    if past_without_score:
        score -= min(25, past_without_score)
        alerts.append(f"{past_without_score} match(s) passes sans score final")

    ratings_age_days = None
    ratings_estimate_count = 0
    ratings_total_teams = 0
    ratings_estimate_pct = None
    r_as_of = _parse_date_ymd(ratings.get("as_of")) if ratings else None
    teams = (ratings or {}).get("teams", {})
    ratings_total_teams = len(teams)
    if ratings_total_teams:
        ratings_estimate_count = sum(
            1 for row in teams.values() if str(row.get("source", "")).lower() != "live"
        )
        ratings_estimate_pct = ratings_estimate_count / ratings_total_teams
        if ratings_estimate_count:
            # Estimated ratings are useful priors but reduce confidence.
            score -= min(25, int(round(ratings_estimate_pct * 35)))
            alerts.append(
                f"ratings estimes: {ratings_estimate_count}/{ratings_total_teams}"
            )
    if r_as_of:
        ratings_age_days = (now - r_as_of).days
        if ratings_age_days > 14:
            score -= min(25, (ratings_age_days - 14))
            alerts.append(f"ratings potentiellement obsoletes ({ratings_age_days} jours)")
    else:
        score -= 15
        alerts.append("ratings.as_of absent")

    status_age_days = None
    status_missing_teams = []
    status_total_teams = ratings_total_teams
    status_coverage_pct = None
    s_as_of = _parse_iso((team_status or {}).get("as_of"))
    status_map = (team_status or {}).get("teams", {})
    if status_total_teams:
        status_missing_teams = [t for t in teams.keys() if t not in status_map]
        covered = status_total_teams - len(status_missing_teams)
        status_coverage_pct = covered / status_total_teams
        if status_missing_teams:
            score -= min(30, int(round((len(status_missing_teams) / status_total_teams) * 40)))
            alerts.append(
                f"team_status incomplet: {covered}/{status_total_teams} equipes"
            )
    if s_as_of:
        status_age_days = (now - s_as_of).days
        if status_age_days > 3:
            score -= min(20, (status_age_days - 3) * 2)
            alerts.append(f"team_status ancien ({status_age_days} jours)")
    else:
        score -= 10
        alerts.append("team_status.as_of absent")

    fixtures_with_home_adv = sum(1 for m in fixtures if m.get("home_adv") is not None)
    home_adv_coverage_pct = fixtures_with_home_adv / len(fixtures) if fixtures else None
    if fixtures_with_home_adv == 0:
        score -= 8
        alerts.append("home_adv absent sur tous les fixtures")

    score = max(0, min(100, int(round(score))))
    if score >= 85:
        level = "good"
    elif score >= 65:
        level = "warning"
    else:
        level = "critical"

    return {
        "score": score,
        "level": level,
        "alerts": alerts,
        "fixtures_missing_dates": missing_dates,
        "fixtures_past_without_score": past_without_score,
        "ratings_age_days": ratings_age_days,
        "ratings_estimate_count": ratings_estimate_count,
        "ratings_total_teams": ratings_total_teams,
        "ratings_estimate_pct": ratings_estimate_pct,
        "status_age_days": status_age_days,
        "status_total_teams": status_total_teams,
        "status_missing_count": len(status_missing_teams),
        "status_coverage_pct": status_coverage_pct,
        "status_missing_sample": status_missing_teams[:12],
        "fixtures_with_home_adv": fixtures_with_home_adv,
        "home_adv_coverage_pct": home_adv_coverage_pct,
    }
