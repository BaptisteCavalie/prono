#!/usr/bin/env python3
"""Freeze pre-match predicted scores into fixtures.json.

This keeps a stable prediction snapshot so UI can compare:
- real score (once match is completed)
- preserved pre-match prediction
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "data" / "fixtures.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import data, model, team_signals, updater


def _sort_key(match):
    return (str(match.get("date") or "9999-99-99"), match.get("matchday", 99), match.get("id", ""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot pre-match predictions into fixtures.json")
    parser.add_argument("--overwrite", action="store_true",
                        help="overwrite existing predicted_home/predicted_away values")
    args = parser.parse_args(argv)

    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures_payload = json.load(f)
    fixtures = fixtures_payload.get("matches", [])

    ratings = data.load_ratings()
    team_status = data.load_team_status()
    ratings, _ = updater.apply_completed_results(ratings, fixtures)
    ratings = team_signals.adjust_ratings_with_status(ratings, team_status)

    updated = 0
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    for m in sorted(fixtures, key=_sort_key):
        if m.get("actual_home") is not None and m.get("actual_away") is not None:
            continue

        has_snapshot = m.get("predicted_home") is not None and m.get("predicted_away") is not None
        if has_snapshot and not args.overwrite:
            continue

        home = m.get("home")
        away = m.get("away")
        if home not in ratings.get("teams", {}) or away not in ratings.get("teams", {}):
            continue

        rh = ratings["teams"][home]
        ra = ratings["teams"][away]
        out = model.analyse(float(rh["rating"]), float(ra["rating"]),
                            home_adv=float(m.get("home_adv", 0.0) or 0.0),
                            ad_home=model.ad_from_row(rh), ad_away=model.ad_from_row(ra))
        (ph, pa), _ = out["top_scores"][0]

        m["predicted_home"] = int(ph)
        m["predicted_away"] = int(pa)
        m["predicted_at"] = now_iso
        updated += 1

    with open(FIXTURES_PATH, "w", encoding="utf-8") as f:
        json.dump(fixtures_payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Snapshots updated: {updated}")
    print(f"fixtures file: {FIXTURES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
