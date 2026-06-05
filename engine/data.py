"""Data loading + fuzzy team-name resolution."""
import json
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ALIASES = {
    "usa": "United States", "us": "United States",
    "united states of america": "United States",
    "turkey": "Türkiye", "turkiye": "Türkiye",
    "korea": "South Korea", "korea republic": "South Korea",
    "dr congo": "DR Congo", "congo dr": "DR Congo", "drc": "DR Congo",
    "democratic republic of the congo": "DR Congo",
    "bosnia": "Bosnia-Herzegovina",
    "bosnia and herzegovina": "Bosnia-Herzegovina",
    "cote d'ivoire": "Ivory Coast", "ivory coast": "Ivory Coast",
    "czech republic": "Czechia",
    "cabo verde": "Cape Verde",
    "saudi": "Saudi Arabia",
    "curacao": "Curaçao",
}


def _load(name: str) -> Dict:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def load_ratings() -> Dict:
    return _load("ratings.json")


def load_groups() -> Dict:
    return {k: v for k, v in _load("groups.json").items()
            if not k.startswith("_")}


def load_fixtures() -> List[Dict]:
    return _load("fixtures.json")["matches"]


def resolve_team(name: str, ratings: Dict) -> Optional[str]:
    """Best-effort map of user input to a canonical team name."""
    if not name:
        return None
    teams = ratings["teams"]
    low = name.strip().lower()
    for t in teams:                       # exact, case-insensitive
        if t.lower() == low:
            return t
    if low in ALIASES and ALIASES[low] in teams:
        return ALIASES[low]
    hits = [t for t in teams if low in t.lower()]  # unique substring
    if len(hits) == 1:
        return hits[0]
    return None
