#!/usr/bin/env python3
"""Build a blank odds template keyed by fixture id and match label.

Examples:
  python3 tools/build_odds_template.py
  python3 tools/build_odds_template.py --matchday 1 --out data/odds_md1.template.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES_FILE = ROOT / "data" / "fixtures.json"
DEFAULT_OUT = ROOT / "data" / "odds.template.json"


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _empty_triplet() -> List[float]:
    return [0.0, 0.0, 0.0]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a fillable 1X2 odds template JSON")
    parser.add_argument("--fixtures-file", default=str(DEFAULT_FIXTURES_FILE), help="path to fixtures.json")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output JSON file")
    parser.add_argument("--matchday", type=int, choices=[1, 2, 3], help="optional filter by matchday")
    args = parser.parse_args(argv)

    fixtures_path = Path(args.fixtures_file).resolve()
    out_path = Path(args.out).resolve()

    fixtures_payload = _read_json(fixtures_path)
    matches = fixtures_payload.get("matches", [])
    if not isinstance(matches, list):
        raise ValueError("fixtures.json must contain a matches array")

    board: Dict[str, List[float]] = {}
    for m in matches:
        if not isinstance(m, dict):
            continue
        if args.matchday and m.get("matchday") != args.matchday:
            continue
        mid = str(m.get("id") or "").strip()
        home = str(m.get("home") or "").strip()
        away = str(m.get("away") or "").strip()
        if not mid or not home or not away:
            continue
        board[mid] = _empty_triplet()
        board[f"{home} vs {away}"] = _empty_triplet()

    _write_json(out_path, board)
    print(f"Wrote {out_path}")
    print(f"keys={len(board)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
