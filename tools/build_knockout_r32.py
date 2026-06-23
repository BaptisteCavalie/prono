#!/usr/bin/env python3
"""Build the 16 Round-of-32 fixtures (matches 73–88) into data/fixtures.json
once the group stage is complete.

Why a separate tool: the R32 *schedule* (match number, date, host city) and the
*slot structure* (who plays whom: 1A, 2B, or a best-third) are fixed and known
in advance — they live in R32_TEMPLATE below. What is NOT derivable from scores
alone is the allocation of the 8 best third-placed teams to the 8 third-slots:
FIFA picks it from a 495-combination table once the 8 qualifying groups are
known. So this tool resolves everything it can deterministically (group winners,
runners-up, the third-place ranking) and reads the third allocation — confirmed
on the official bracket by the ask-Claude layer — from data/knockout_seed.json.

Usage:
    python3 tools/build_knockout_r32.py            # report (read-only): standings + what's missing
    python3 tools/build_knockout_r32.py --write     # compose + write the 16 R32 fixtures

Règle d'or (cf. /maj-resultats): on ne devine jamais un appariement. Groupe non
terminé, classement à égalité non tranchée, allocation des 3es absente → on
n'écrit pas et on le signale.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))

from engine import home_advantage, standings  # noqa: E402

# Fixed Round-of-32 schedule and slot structure (FIFA / Wikipedia, WC 2026).
# slot syntax: "1X" = winner group X, "2X" = runner-up group X,
# "3:XYZ..." = the best third drawn from one of those groups (FIFA table).
R32_TEMPLATE = [
    ("K73", 73, "2026-06-28", "Inglewood, CA",     "2A",      "2B"),
    ("K74", 74, "2026-06-29", "Foxborough, MA",     "1E",      "3:ABCDF"),
    ("K75", 75, "2026-06-29", "Guadalupe, Mexico",  "1F",      "2C"),
    ("K76", 76, "2026-06-29", "Houston, TX",        "1C",      "2F"),
    ("K77", 77, "2026-06-30", "East Rutherford, NJ","1I",      "3:CDFGH"),
    ("K78", 78, "2026-06-30", "Arlington, TX",      "2E",      "2I"),
    ("K79", 79, "2026-06-30", "Mexico City",        "1A",      "3:CEFHI"),
    ("K80", 80, "2026-07-01", "Atlanta, GA",        "1L",      "3:EHIJK"),
    ("K81", 81, "2026-07-01", "Santa Clara, CA",    "1D",      "3:BEFIJ"),
    ("K82", 82, "2026-07-01", "Seattle, WA",        "1G",      "3:AEHIJ"),
    ("K83", 83, "2026-07-02", "Toronto",            "2K",      "2L"),
    ("K84", 84, "2026-07-02", "Inglewood, CA",      "1H",      "2J"),
    ("K85", 85, "2026-07-02", "Vancouver",          "1B",      "3:EFGIJ"),
    ("K86", 86, "2026-07-03", "Miami Gardens, FL",  "1J",      "2H"),
    ("K87", 87, "2026-07-03", "Kansas City, MO",    "1K",      "3:DEIJL"),
    ("K88", 88, "2026-07-03", "Arlington, TX",      "2D",      "2G"),
]


def _seed() -> dict:
    path = DATA / "knockout_seed.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text("utf-8"))


def _resolve_slot(slot, st, thirds_by_match, match_no, third_groups, errors):
    """Resolve one slot label to a team name, recording any problem in errors."""
    kind, ref = slot[0], slot[1:]
    if kind == "1":
        return st["winners"].get(ref)
    if kind == "2":
        return st["runners_up"].get(ref)
    # third-place slot "3:XYZ"
    allowed = set(ref.lstrip(":"))
    g = thirds_by_match.get(str(match_no))
    if not g:
        errors.append(f"M{match_no}: allocation du 3e manquante (data/knockout_seed.json → thirds_by_match[\"{match_no}\"], au choix {sorted(allowed)})")
        return None
    if g not in allowed:
        errors.append(f"M{match_no}: 3e du groupe {g} hors des candidats autorisés {sorted(allowed)}")
        return None
    if g not in third_groups:
        errors.append(f"M{match_no}: groupe {g} n'a pas de 3e qualifié (les 8 qualifiés : {sorted(third_groups)})")
        return None
    return third_groups[g]


def compose(matches, seed=None):
    st = standings.final_standings(matches)
    seed = _seed() if seed is None else seed
    thirds_by_match = {str(k): v for k, v in (seed.get("thirds_by_match") or {}).items()}
    # map group -> third team for the 8 qualified thirds
    third_groups = {g: team for g, team, _ in st["best_thirds"]}

    errors = []
    if st["incomplete"]:
        errors.append(f"Phase de groupes incomplète — groupes en cours : {', '.join(st['incomplete'])}")
    for tied in st["ties"]:
        errors.append(f"Égalité non tranchée (à confirmer sur la table officielle) : {', '.join(sorted(tied))}")

    fixtures = []
    for fid, no, date, venue, hs, as_ in R32_TEMPLATE:
        home = _resolve_slot(hs, st, thirds_by_match, no, third_groups, errors)
        away = _resolve_slot(as_, st, thirds_by_match, no, third_groups, errors)
        fixtures.append({
            "id": fid, "match_no": no, "stage": "round_of_32",
            "home_slot": hs, "away_slot": as_,
            "home": home, "away": away,
            "venue": venue, "date": date, "kickoff_utc": None,
            "home_adv": home_advantage.home_adv_for(home or "", away or ""),
            "actual_home": None, "actual_away": None,
        })

    # No team may appear twice across the 16 fixtures.
    seen = {}
    for fx in fixtures:
        for t in (fx["home"], fx["away"]):
            if t:
                if t in seen:
                    errors.append(f"{t} apparaît deux fois ({seen[t]} et {fx['id']})")
                seen[t] = fx["id"]
    return st, fixtures, errors


def _print_report(st, fixtures, errors):
    print("=== Classements finaux (phase de groupes) ===")
    if st["incomplete"]:
        print(f"  Groupes NON terminés : {', '.join(st['incomplete'])}")
    for g in sorted(st["winners"]):
        print(f"  {g}: 1er {st['winners'][g]:24s} 2e {st['runners_up'][g]}")
    print("\n=== 3es classés (8 premiers qualifiés) ===")
    for i, (g, team, row) in enumerate(st["thirds_ranked"], 1):
        mark = "✓" if i <= 8 else "✗"
        print(f"  {mark} #{i} {team:22s} (Gr.{g}, {row['pts']} pts, diff {row['gd']:+d}, {row['gf']} bp)")
    print("\n=== Round of 32 ===")
    for fx in fixtures:
        h = fx["home"] or f"<{fx['home_slot']}>"
        a = fx["away"] or f"<{fx['away_slot']}>"
        print(f"  M{fx['match_no']} {fx['date']} {fx['venue']:22s} {h} vs {a}")
    if errors:
        print("\n!!! À résoudre avant écriture :")
        for e in errors:
            print(f"  - {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="écrire les 16 fixtures R32 dans data/fixtures.json")
    args = ap.parse_args()

    data = json.loads((DATA / "fixtures.json").read_text("utf-8"))
    matches = data["matches"]
    st, r32, errors = compose(matches)
    _print_report(st, r32, errors)

    if not args.write:
        return
    if errors:
        print("\nÉcriture annulée (erreurs ci-dessus).")
        sys.exit(1)

    others = [m for m in matches if str(m.get("stage") or "group") == "group"]
    data["matches"] = others + r32
    (DATA / "fixtures.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(r32)} fixtures Round of 32 écrites dans {DATA / 'fixtures.json'}.")


if __name__ == "__main__":
    main()
