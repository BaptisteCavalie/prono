#!/usr/bin/env python3
"""Settle the real Winamax bets in data/bets.json from match results.

The MPP/odds layer feeds results into data/fixtures.json (cf. /maj-resultats);
this tool turns those results into bet outcomes so the Paris tab's P&L/ROI stays
current without Baptiste having to dictate every settlement.

Deterministic and idempotent: it only ever moves an ``en_cours`` bet to
``gagne``/``perdu`` once its legs are decided (engine.common.settle_status —
a combo loses on any losing leg, wins only when every leg is played and won),
writes nothing when no status changes, and never invents a refund (voided /
cancelled selections stay manual — they're flagged, not guessed). Settlement
logic is money logic: it lives in engine.common and is tested (tests/test_bets.py).

Run:  python3 tools/settle_bets.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "data" / "fixtures.json"
BETS_PATH = ROOT / "data" / "bets.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import common


def results_from_fixtures(fixtures) -> dict:
    """`{MATCH_ID: (home_goals, away_goals)}` for finished matches only."""
    out = {}
    for m in fixtures:
        h, a = m.get("actual_home"), m.get("actual_away")
        if h is not None and a is not None:
            out[str(m.get("id", "")).upper()] = (int(h), int(a))
    return out


def main(argv=None) -> int:
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures = json.load(f).get("matches", [])
    with open(BETS_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    bets = payload.get("bets", [])

    results = results_from_fixtures(fixtures)
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    changed = []
    for b in bets:
        if common.bet_status(b) != "en_cours":
            continue                         # never touch an already-settled bet
        new_status = common.settle_status(b, results)
        if new_status != "en_cours":
            b["status"] = new_status
            b["settled_at"] = now_iso
            changed.append((b, new_status))

    if not changed:
        print("settle_bets : aucun pari à régler (rien de neuf parmi les en cours).")
        return 0

    with open(BETS_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    for b, st in changed:
        ref = b.get("ref") or f"id {b.get('id')}"
        net = common.bet_net(b)
        net_txt = "—" if net is None else f"{net:+.2f} €"
        print(f"  {ref} : {b.get('label', '')} -> {st} ({net_txt})")
    print(f"settle_bets : {len(changed)} pari(s) réglé(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
