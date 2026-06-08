#!/usr/bin/env python3
"""Merge per-team scoring profiles (goals for/against per game) into ratings.json.

These feed the model's attack/defense multipliers (engine/model.py:ad_from_row),
which shape the goal total -> Over/Under 2.5 and BTTS. Offline only: like the
ratings, real numbers come from the "ask Claude" refresh layer; values written
here are tagged with a scoring_source so estimates stay visible.

Examples:
  python3 tools/update_team_scoring.py --team "Germany" --gf 2.2 --ga 1.1 --source estimate
  python3 tools/update_team_scoring.py --merge-file data/team_scoring_seed.json --source estimate
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RATINGS_FILE = ROOT / "data" / "ratings.json"

GF_RANGE = (0.2, 4.0)   # plausible goals-for per game
GA_RANGE = (0.2, 4.0)   # plausible goals-against per game


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _clamp(name: str, value: float, lo: float, hi: float) -> float:
    v = float(value)
    if v < lo or v > hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}] (got {v})")
    return round(v, 3)


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _apply(teams: Dict[str, Any], team: str, gf, ga, source: str) -> bool:
    if team not in teams:
        return False
    row = teams[team]
    if not isinstance(row, dict):
        return False
    if gf is not None:
        row["goals_for_pg"] = _clamp("goals_for_pg", gf, *GF_RANGE)
    if ga is not None:
        row["goals_against_pg"] = _clamp("goals_against_pg", ga, *GA_RANGE)
    if "goals_for_pg" in row and "goals_against_pg" in row:
        row["scoring_source"] = source
    return True


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Update per-team scoring profiles in ratings.json")
    p.add_argument("--file", default=str(DEFAULT_RATINGS_FILE), help="path to ratings.json")
    p.add_argument("--source", default="estimate", help="scoring_source tag (estimate|live|...)")
    p.add_argument("--team", help="single team to update")
    p.add_argument("--gf", type=float, help="goals for per game")
    p.add_argument("--ga", type=float, help="goals against per game")
    p.add_argument("--merge-file", help="JSON {teams:{Team:{goals_for_pg,goals_against_pg}}} or {Team:{...}}")
    p.add_argument("--dry-run", action="store_true", help="print result without writing")
    args = p.parse_args(argv)

    path = Path(args.file).resolve()
    payload = _read_json(path)
    teams = payload.get("teams", {})
    if not isinstance(teams, dict):
        raise ValueError("ratings.json must contain a 'teams' object")

    if not args.team and not args.merge_file:
        p.error("Provide --team (with --gf/--ga) and/or --merge-file")

    applied = 0
    skipped: List[str] = []

    if args.team:
        if _apply(teams, args.team, args.gf, args.ga, args.source):
            applied += 1
        else:
            skipped.append(args.team)

    if args.merge_file:
        incoming = _read_json(Path(args.merge_file).resolve())
        incoming_teams = incoming.get("teams", incoming)
        if not isinstance(incoming_teams, dict):
            raise ValueError("merge-file must be {teams:{...}} or {Team:{...}}")
        for team, entry in incoming_teams.items():
            if not isinstance(entry, dict):
                continue
            gf = entry.get("goals_for_pg", entry.get("gf"))
            ga = entry.get("goals_against_pg", entry.get("ga"))
            src = entry.get("scoring_source", args.source)
            if _apply(teams, str(team), gf, ga, src):
                applied += 1
            else:
                skipped.append(str(team))

    covered = sum(1 for r in teams.values()
                  if isinstance(r, dict) and "goals_for_pg" in r and "goals_against_pg" in r)
    payload["scoring_as_of"] = _iso_now_utc()

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    _write_json(path, payload)
    print(f"Updated {path}")
    print(f"applied={applied}  skipped={skipped or '-'}")
    print(f"scoring coverage: {covered}/{len(teams)} teams")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
