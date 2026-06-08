#!/usr/bin/env python3
"""Generate data/fixtures.json (72 group matches) from data/groups.json.

Uses the standard FIFA 4-team round-robin matchday pattern. Re-run whenever
groups.json changes. Knockout fixtures are added separately once the bracket
is known.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))

from engine import home_advantage  # noqa: E402

# Standard 4-team schedule by draw position (0-indexed): two matches per round.
PATTERN = [(0, 1), (2, 3), (0, 2), (3, 1), (3, 0), (1, 2)]
MATCHDAY = [1, 1, 2, 2, 3, 3]


def main() -> None:
    groups = {k: v for k, v in json.loads((DATA / "groups.json").read_text("utf-8")).items()
              if not k.startswith("_")}
    matches = []
    n = 1
    for g in sorted(groups):
        teams = groups[g]
        for (h, a), md in zip(PATTERN, MATCHDAY):
            home, away = teams[h], teams[a]
            adv = home_advantage.home_adv_for(home, away)
            matches.append({
                "id": f"G{n:02d}",
                "stage": "group",
                "group": g,
                "matchday": md,
                "home": home,
                "away": away,
                "venue": home_advantage.host_venue_label(home, away) or "neutral",
                "date": None,
                "home_adv": adv,
                "actual_home": None,
                "actual_away": None,
            })
            n += 1
    (DATA / "fixtures.json").write_text(
        json.dumps({"matches": matches}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"{len(matches)} fixtures written to {DATA / 'fixtures.json'}")


if __name__ == "__main__":
    main()
