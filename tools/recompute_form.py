#!/usr/bin/env python3
"""Recompute the recent-form signal in data/team_status.json from results.

Form is the model's momentum channel, derived from each team's completed
fixtures (see engine/form.py). Only the ``form`` field is rewritten — injuries,
suspensions, news risk and notes (ask-Claude layer) are preserved. Run after
recording new scores (e.g. from /maj-resultats):

  python3 tools/recompute_form.py            # write team_status.json
  python3 tools/recompute_form.py --dry-run  # preview the changes only
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import data, form

STATUS_FILE = ROOT / "data" / "team_status.json"


def _iso_now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute form from completed fixtures")
    parser.add_argument("--dry-run", action="store_true", help="print changes without writing")
    args = parser.parse_args(argv)

    fixtures = data.load_fixtures()
    ratings = data.load_ratings()
    with open(STATUS_FILE, encoding="utf-8") as f:
        team_status = json.load(f)

    _, changes = form.recompute_form(team_status, fixtures, ratings)

    if not changes:
        print("Aucune forme à mettre à jour (pas de match terminé, ou déjà à jour).")
        return 0

    for team, old_form, new_form in changes:
        arrow = "↑" if new_form > old_form else "↓"
        print(f"{team}: {old_form:+.2f} → {new_form:+.2f} {arrow}")
    print(f"--- {len(changes)} équipe(s) recalculée(s)")

    if args.dry_run:
        return 0

    team_status["as_of"] = _iso_now_utc()
    team_status["source"] = "form_from_results"
    _write_json(STATUS_FILE, team_status)
    print(f"Écrit {STATUS_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
