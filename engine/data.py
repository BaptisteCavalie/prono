"""Data loading + fuzzy team-name resolution."""
import json
from pathlib import Path
from typing import Dict, List, Optional

from engine import home_advantage

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
    matches = _load("fixtures.json")["matches"]
    for m in matches:
        # Host-nation home advantage is fully derivable from the two team names,
        # so derive it authoritatively on load. This is the single source of
        # truth (engine/home_advantage.py) and stays correct even if a cached
        # home_adv in the data file is stale or partial — notably it credits a
        # host playing as the *away* team (negative home_adv), which a naive
        # "home team only" fill misses. Set `home_adv_manual: true` on a fixture
        # to opt out (e.g. a real neutral-site game inside a host country).
        if not m.get("home_adv_manual"):
            adv = home_advantage.home_adv_for(m.get("home", ""), m.get("away", ""))
            m["home_adv"] = adv
            if adv and m.get("venue") in (None, "", "neutral"):
                m["venue"] = home_advantage.host_venue_label(m["home"], m["away"])
    return matches


def load_team_status() -> Dict:
    path = DATA_DIR / "team_status.json"
    if not path.is_file():
        return {"as_of": None, "teams": {}, "source": "missing"}
    return _load("team_status.json")


def load_bets() -> List[Dict]:
    """Paris réels suivis (data/bets.json), écrits par la couche ask-Claude.

    Schéma d'une ligne : ``id``, ``label`` (match ou « Combiné N sél. »),
    ``sel``, ``odds``, ``stake``, ``status`` (gagne|perdu|rembourse|en_cours) ;
    optionnels ``combo``, ``date``, ``closing``. Fichier optionnel (absent tant
    qu'aucun pari n'est enregistré → liste vide) et tolérant à un JSON cassé :
    ne jamais faire planter la page Paris pour un fichier de suivi mal formé.
    """
    try:
        with open(DATA_DIR / "bets.json", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    bets = raw.get("bets") if isinstance(raw, dict) else raw
    return [b for b in bets if isinstance(b, dict)] if isinstance(bets, list) else []


def load_mpp_board() -> Dict[str, List[float]]:
    """Real Mon Petit Prono "bon résultat" points per match (data/mpp_board.json),
    written by the ask-Claude layer like scores/bets/odds.

    Shape: ``{FIXTURE_ID: [points_home, points_draw, points_away]}`` — the three
    point values shown under each outcome in the MPP app. MPP's barème is
    proprietary (tracks the cote, compressed), so these real numbers beat any
    odds-derived approximation when computing the points-optimal prono. Optional
    file (absent → empty), tolerant of broken JSON: a malformed tracking file
    must never crash the Matchs page. Keys are upper-cased to match fixture ids.
    """
    try:
        with open(DATA_DIR / "mpp_board.json", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    board: Dict[str, List[float]] = {}
    for key, triple in raw.items():
        if (isinstance(triple, list) and len(triple) == 3
                and all(isinstance(x, (int, float)) for x in triple)):
            board[str(key).upper()] = [float(x) for x in triple]
    return board


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
