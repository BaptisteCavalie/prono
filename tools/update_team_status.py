#!/usr/bin/env python3
"""Quick editor for data/team_status.json.

Examples:
  python3 tools/update_team_status.py --team "France" --form 0.25 --injury 0.05 --news 0.03 --note "retour du capitaine"
  python3 tools/update_team_status.py --merge-file data/team_status_patch.json --source news_digest
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS_FILE = ROOT / "data" / "team_status.json"


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _clamp(name: str, value: float, lo: float, hi: float) -> float:
    if value < lo or value > hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}]")
    return round(float(value), 4)


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_team_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "form": _clamp("form", float(entry.get("form", 0.0) or 0.0), -1.0, 1.0),
        "injury_impact": _clamp("injury_impact", float(entry.get("injury_impact", 0.0) or 0.0), 0.0, 1.0),
        "suspension_impact": _clamp("suspension_impact", float(entry.get("suspension_impact", 0.0) or 0.0), 0.0, 1.0),
        "news_risk": _clamp("news_risk", float(entry.get("news_risk", 0.0) or 0.0), 0.0, 1.0),
    }
    notes = entry.get("notes")
    if isinstance(notes, list):
        out["notes"] = [str(n).strip() for n in notes if str(n).strip()]
    return out


def _validate_required_signals(payload: Dict[str, Any]) -> None:
    teams = payload.get("teams", {})
    if not isinstance(teams, dict):
        raise ValueError("teams must be an object")
    required = ["form", "injury_impact", "suspension_impact", "news_risk"]
    missing = []
    for team, entry in teams.items():
        if not isinstance(entry, dict):
            missing.append(f"{team}: invalid entry")
            continue
        absent = [k for k in required if k not in entry]
        if absent:
            missing.append(f"{team}: missing {', '.join(absent)}")
    if missing:
        lines = "\n - ".join(missing)
        raise ValueError("strict validation failed:\n - " + lines)


def _apply_single_team_update(payload: Dict[str, Any], args: argparse.Namespace) -> None:
    teams = payload.setdefault("teams", {})
    current = dict(teams.get(args.team, {}))

    if args.form is not None:
        current["form"] = _clamp("form", args.form, -1.0, 1.0)
    if args.injury is not None:
        current["injury_impact"] = _clamp("injury_impact", args.injury, 0.0, 1.0)
    if args.suspension is not None:
        current["suspension_impact"] = _clamp("suspension_impact", args.suspension, 0.0, 1.0)
    if args.news is not None:
        current["news_risk"] = _clamp("news_risk", args.news, 0.0, 1.0)

    if args.note:
        notes: List[str] = [str(n).strip() for n in (current.get("notes") or []) if str(n).strip()]
        for note in args.note:
            if note.strip():
                notes.append(note.strip())
        current["notes"] = notes

    teams[args.team] = _normalize_team_entry(current)


def _apply_merge_file(payload: Dict[str, Any], merge_path: Path) -> None:
    incoming = _read_json(merge_path)
    if not isinstance(incoming, dict):
        raise ValueError("merge-file must be a JSON object")

    incoming_teams = incoming.get("teams", incoming)
    if not isinstance(incoming_teams, dict):
        raise ValueError("merge-file must contain a 'teams' object or be a {team: entry} object")

    teams = payload.setdefault("teams", {})
    for team, entry in incoming_teams.items():
        if not isinstance(entry, dict):
            continue
        base = dict(teams.get(team, {}))
        base.update(entry)
        teams[str(team)] = _normalize_team_entry(base)


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update data/team_status.json quickly")
    parser.add_argument("--file", default=str(DEFAULT_STATUS_FILE), help="path to team_status.json")
    parser.add_argument("--source", default="manual_cli", help="metadata source tag")
    parser.add_argument("--team", help="single team to update")
    parser.add_argument("--form", type=float, help="form in [-1, 1]")
    parser.add_argument("--injury", type=float, help="injury impact in [0, 1]")
    parser.add_argument("--suspension", type=float, help="suspension impact in [0, 1]")
    parser.add_argument("--news", type=float, help="news risk in [0, 1]")
    parser.add_argument("--note", action="append", help="append a note for --team (repeatable)")
    parser.add_argument("--merge-file", help="JSON file containing {teams:{...}} or {team:{...}} updates")
    parser.add_argument("--strict", action="store_true",
                        help="require every team to have form/injury_impact/suspension_impact/news_risk")
    parser.add_argument("--dry-run", action="store_true", help="print output without writing file")
    args = parser.parse_args(argv)

    status_path = Path(args.file).resolve()
    if not status_path.exists():
        raise FileNotFoundError(f"status file not found: {status_path}")

    payload = _read_json(status_path)
    if not isinstance(payload, dict):
        raise ValueError("status file must be a JSON object")

    if not args.team and not args.merge_file:
        parser.error("Provide --team for single update and/or --merge-file for bulk updates")

    if args.team:
        _apply_single_team_update(payload, args)

    if args.merge_file:
        _apply_merge_file(payload, Path(args.merge_file).resolve())

    payload["as_of"] = _iso_now_utc()
    payload["source"] = str(args.source).strip() or "manual_cli"

    if args.strict:
        _validate_required_signals(payload)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    _write_json(status_path, payload)
    print(f"Updated {status_path}")
    print(f"as_of={payload['as_of']}")
    print(f"source={payload['source']}")
    print(f"teams={len(payload.get('teams', {}))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
