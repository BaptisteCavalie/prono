"""Autonomous data refresh pipeline.

Best-effort updater that can run on each CLI/UI/API call:
- fetch live Elo ratings from eloratings.net TSV endpoints
- ensure fixtures have home_adv values
- ensure team_status covers every rated team
- refresh saved fixture predictions when upstream inputs change
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.request import urlopen

from engine import data, expert_signals, prediction, team_signals, updater

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RATINGS_PATH = DATA_DIR / "ratings.json"
FIXTURES_PATH = DATA_DIR / "fixtures.json"
STATUS_PATH = DATA_DIR / "team_status.json"
STATE_PATH = DATA_DIR / ".auto_refresh_state.json"

ELO_BASE = "https://www.eloratings.net"
WORLD_TSV = f"{ELO_BASE}/World.tsv"
TEAMS_TSV = f"{ELO_BASE}/en.teams.tsv"
LATEST_TSV = f"{ELO_BASE}/latest.tsv"

HOSTS = {"Mexico", "Canada", "United States"}
DEFAULT_HOME_ADV = 0.0
HOST_HOME_ADV = 65.0
DEFAULT_STATUS = {
    "form": 0.0,
    "injury_impact": 0.0,
    "suspension_impact": 0.0,
    "news_risk": 0.0,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _fetch_tsv_lines(url: str, timeout: int = 20) -> List[str]:
    with urlopen(url, timeout=timeout) as r:
        txt = r.read().decode("utf-8", errors="ignore")
    return [ln.strip() for ln in txt.splitlines() if ln.strip()]


def _parse_team_names() -> Dict[str, str]:
    lines = _fetch_tsv_lines(TEAMS_TSV)
    out: Dict[str, str] = {}
    for ln in lines:
        parts = [p.strip() for p in ln.split("\t") if p.strip()]
        if len(parts) < 2:
            continue
        out[parts[0]] = parts[1]
    return out


def _parse_world_ratings() -> Dict[str, int]:
    lines = _fetch_tsv_lines(WORLD_TSV)
    out: Dict[str, int] = {}
    for ln in lines:
        parts = [p.strip() for p in ln.split("\t") if p.strip()]
        if len(parts) < 4:
            continue
        code = parts[2]
        try:
            rating = int(float(parts[3]))
        except ValueError:
            continue
        out[code] = rating
    return out


def _parse_latest_as_of() -> str:
    lines = _fetch_tsv_lines(LATEST_TSV)
    latest = None
    for ln in lines:
        parts = [p.strip() for p in ln.split("\t") if p.strip()]
        if len(parts) < 3:
            continue
        y, m, d = parts[0], parts[1], parts[2]
        if not (y.isdigit() and m.isdigit() and d.isdigit()):
            continue
        iso = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        if latest is None or iso > latest:
            latest = iso
    return latest or datetime.now(timezone.utc).date().isoformat()


def _refresh_live_ratings(ratings_payload: Dict) -> Tuple[int, int, str]:
    code_to_name = _parse_team_names()
    code_to_rating = _parse_world_ratings()
    as_of = _parse_latest_as_of()

    teams = ratings_payload.get("teams", {})
    updated = 0
    matched = 0
    seen = set()
    changed = set()

    for code, rating in code_to_rating.items():
        src_name = code_to_name.get(code)
        if not src_name:
            continue
        canonical = data.resolve_team(src_name, ratings_payload)
        if not canonical or canonical not in teams:
            continue
        seen.add(canonical)
        row = teams[canonical]
        old_rating = float(row.get("rating", 0.0))
        old_source = str(row.get("source", ""))
        if old_rating != float(rating) or old_source.lower() != "live":
            row["rating"] = int(rating)
            row["source"] = "live"
            changed.add(canonical)

    matched = len(seen)
    updated = len(changed)

    ratings_payload["as_of"] = as_of
    ratings_payload["source"] = (
        "World Football Elo auto-refresh via eloratings.net TSV endpoints "
        f"(last refresh {_iso_now()})"
    )
    return updated, matched, as_of


def _refresh_home_adv(fixtures_payload: Dict) -> int:
    # home_adv is added to the HOME side's rating (engine/model.py), so a host
    # listed as the away team gets its boost as a NEGATIVE home_adv. Two hosts
    # facing each other cancel out to 0.
    updated = 0
    for m in fixtures_payload.get("matches", []):
        target = DEFAULT_HOME_ADV
        if m.get("home") in HOSTS:
            target += HOST_HOME_ADV
        if m.get("away") in HOSTS:
            target -= HOST_HOME_ADV
        current = float(m.get("home_adv", 0.0) or 0.0)
        if current != target:
            m["home_adv"] = target
            updated += 1
    return updated


def _refresh_team_status_coverage(status_payload: Dict, ratings_payload: Dict) -> int:
    teams = ratings_payload.get("teams", {})
    status_teams = status_payload.setdefault("teams", {})
    added = 0
    for team in teams.keys():
        if team in status_teams and isinstance(status_teams[team], dict):
            continue
        status_teams[team] = dict(DEFAULT_STATUS)
        added += 1
    status_payload["as_of"] = _iso_now()
    status_payload["source"] = "autonomous_refresh"
    return added


def _refresh_prediction_snapshots(fixtures_payload: Dict, ratings_payload: Dict,
                                  status_payload: Optional[Dict] = None) -> int:
    updated = 0
    now_iso = _iso_now()
    matches = fixtures_payload.get("matches", [])

    # Freeze from the SAME ratings the UI computes its live prono from: a copy
    # with completed-result and team-signal adjustments applied (never baked back
    # into ratings.json). The scoreline itself goes through the one shared helper
    # (engine/prediction.py) so the frozen prono and the displayed prono can't
    # drift apart and fire a spurious "Prono mis a jour" flag on the UI.
    ratings_for_pred = copy.deepcopy(ratings_payload)
    ratings_for_pred, _ = updater.apply_completed_results(ratings_for_pred, matches)
    if status_payload is not None:
        ratings_for_pred = team_signals.adjust_ratings_with_status(ratings_for_pred, status_payload)
    ratings_for_pred = expert_signals.apply_expert_priors(ratings_for_pred)

    for m in matches:
        if m.get("actual_home") is not None and m.get("actual_away") is not None:
            continue
        sl = prediction.scoreline(m, ratings_for_pred)
        if sl is None:
            continue
        ph, pa = sl

        if m.get("predicted_home") != ph or m.get("predicted_away") != pa:
            m["predicted_home"] = ph
            m["predicted_away"] = pa
            m["predicted_at"] = now_iso
            updated += 1
    return updated


def _data_dir_writable() -> bool:
    """False on read-only/serverless hosts (Vercel, Lambda) where the app bundle
    is mounted read-only. The refresh writes back into data/, so attempting it
    there only burns latency and raises on write — skip it cleanly instead."""
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return False
    try:
        return os.access(DATA_DIR, os.W_OK)
    except OSError:
        return False


def _should_run(cooldown_minutes: int) -> bool:
    if cooldown_minutes <= 0:
        return True
    if not STATE_PATH.is_file():
        return True
    try:
        state = _read_json(STATE_PATH)
        last = str(state.get("last_run_at") or "")
        if not last:
            return True
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        age_seconds = (datetime.now(timezone.utc) - dt).total_seconds()
        return age_seconds >= cooldown_minutes * 60
    except Exception:
        return True


def _mark_run(report: Dict) -> None:
    payload = {
        "last_run_at": _iso_now(),
        "last_report": report,
    }
    _write_json(STATE_PATH, payload)


def autonomous_refresh(force: bool = False, cooldown_minutes: int = 180) -> Dict:
    report = {
        "ran": False,
        "skipped": False,
        "reason": "",
        "ratings_updated": 0,
        "ratings_matched": 0,
        "ratings_as_of": None,
        "home_adv_updated": 0,
        "team_status_added": 0,
        "predictions_updated": 0,
        "errors": [],
    }

    if not _data_dir_writable():
        report["skipped"] = True
        report["reason"] = "read_only_fs"
        return report

    if not force and not _should_run(cooldown_minutes):
        report["skipped"] = True
        report["reason"] = f"cooldown_{cooldown_minutes}m"
        return report

    ratings_payload = _read_json(RATINGS_PATH)
    fixtures_payload = _read_json(FIXTURES_PATH)
    status_payload = _read_json(STATUS_PATH) if STATUS_PATH.is_file() else {"teams": {}}

    try:
        upd, matched, as_of = _refresh_live_ratings(ratings_payload)
        report["ratings_updated"] = upd
        report["ratings_matched"] = matched
        report["ratings_as_of"] = as_of
    except Exception as exc:
        report["errors"].append(f"ratings_refresh_failed: {exc}")

    try:
        report["home_adv_updated"] = _refresh_home_adv(fixtures_payload)
    except Exception as exc:
        report["errors"].append(f"home_adv_refresh_failed: {exc}")

    try:
        report["team_status_added"] = _refresh_team_status_coverage(status_payload, ratings_payload)
    except Exception as exc:
        report["errors"].append(f"team_status_refresh_failed: {exc}")

    try:
        report["predictions_updated"] = _refresh_prediction_snapshots(fixtures_payload, ratings_payload, status_payload)
    except Exception as exc:
        report["errors"].append(f"prediction_refresh_failed: {exc}")

    try:
        _write_json(RATINGS_PATH, ratings_payload)
        _write_json(FIXTURES_PATH, fixtures_payload)
        _write_json(STATUS_PATH, status_payload)
        report["ran"] = True
        _mark_run(report)
    except OSError as exc:
        # Never let a best-effort write blow up the caller (e.g. read-only host).
        report["skipped"] = True
        report["reason"] = "write_failed"
        report["errors"].append(f"write_failed: {exc}")
    return report
