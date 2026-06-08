#!/usr/bin/env python3
"""Create missing team_status entries for all teams in ratings.json.

Examples:
  python3 tools/bootstrap_team_status.py
  python3 tools/bootstrap_team_status.py --dry-run
  python3 tools/bootstrap_team_status.py --default-form -0.05 --note "auto-seeded"
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RATINGS_FILE = ROOT / "data" / "ratings.json"
DEFAULT_STATUS_FILE = ROOT / "data" / "team_status.json"


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clamp(name: str, value: float, lo: float, hi: float) -> float:
    if value < lo or value > hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}]")
    return round(float(value), 4)


def _default_entry(form: float, injury: float, suspension: float, news: float, note: str | None) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "form": _clamp("default-form", form, -1.0, 1.0),
        "injury_impact": _clamp("default-injury", injury, 0.0, 1.0),
        "suspension_impact": _clamp("default-suspension", suspension, 0.0, 1.0),
        "news_risk": _clamp("default-news", news, 0.0, 1.0),
    }
    if note and note.strip():
        out["notes"] = [note.strip()]
    return out


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap missing team_status entries for every rated team")
    parser.add_argument("--ratings-file", default=str(DEFAULT_RATINGS_FILE), help="path to ratings.json")
    parser.add_argument("--status-file", default=str(DEFAULT_STATUS_FILE), help="path to team_status.json")
    parser.add_argument("--source", default="bootstrap_status", help="source metadata tag")
    parser.add_argument("--default-form", type=float, default=0.0, help="default form in [-1,1]")
    parser.add_argument("--default-injury", type=float, default=0.0, help="default injury_impact in [0,1]")
    parser.add_argument("--default-suspension", type=float, default=0.0, help="default suspension_impact in [0,1]")
    parser.add_argument("--default-news", type=float, default=0.0, help="default news_risk in [0,1]")
    parser.add_argument("--note", help="optional note added to newly created entries")
    parser.add_argument("--dry-run", action="store_true", help="print summary without writing")
    args = parser.parse_args(argv)

    ratings_path = Path(args.ratings_file).resolve()
    status_path = Path(args.status_file).resolve()

    ratings = _read_json(ratings_path)
    if not isinstance(ratings, dict) or not isinstance(ratings.get("teams"), dict):
        raise ValueError("ratings file must contain a teams object")

    if status_path.exists():
        status = _read_json(status_path)
        if not isinstance(status, dict):
            raise ValueError("status file must be a JSON object")
    else:
        status = {}

    status_teams = status.setdefault("teams", {})
    if not isinstance(status_teams, dict):
        raise ValueError("status.teams must be an object")

    template = _default_entry(
        args.default_form,
        args.default_injury,
        args.default_suspension,
        args.default_news,
        args.note,
    )

    added = []
    for team in ratings["teams"].keys():
        if team in status_teams and isinstance(status_teams[team], dict):
            continue
        status_teams[team] = dict(template)
        added.append(team)

    status["as_of"] = _iso_now_utc()
    status["source"] = str(args.source).strip() or "bootstrap_status"

    if args.dry_run:
        print(f"would add {len(added)} missing team_status entries")
        if added:
            print("sample:")
            for team in added[:12]:
                print(f" - {team}")
        return 0

    _write_json(status_path, status)
    print(f"Updated {status_path}")
    print(f"added_missing_entries={len(added)}")
    print(f"total_status_teams={len(status_teams)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
