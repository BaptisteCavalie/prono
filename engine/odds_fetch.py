"""Auto-fetch 1X2 (h2h) odds from The Odds API -> data/odds.json.

Free tier, but it needs a one-time free API key (https://the-odds-api.com).
Provide it via the env var ODDS_API_KEY or a file data/odds_api_key.txt. Without
a key (or offline / out of season), every function degrades cleanly: the fetch is
skipped and any existing data/odds.json is left untouched, so the Paris page keeps
working on whatever odds are already there.

We take the *median* decimal price across EU bookmakers per outcome (a simple
consensus that ignores any single book's outlier or extra margin), orient it to
each fixture's home/away order, and key the board by fixture id (e.g. "G01"),
exactly the format engine/odds.py + the UI loader expect.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from engine import data

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ODDS_PATH = DATA_DIR / "odds.json"
STATE_PATH = DATA_DIR / ".odds_state.json"
KEY_FILE = DATA_DIR / "odds_api_key.txt"

API_BASE = "https://api.the-odds-api.com/v4"
DEFAULT_SPORT = "soccer_fifa_world_cup"
REGIONS = "eu"
MARKETS = "h2h"


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_key() -> str:
    key = (os.environ.get("ODDS_API_KEY") or "").strip()
    if key:
        return key
    if KEY_FILE.is_file():
        try:
            return KEY_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def has_key() -> bool:
    return bool(get_key())


def _http_json(url: str, timeout: int = 20):
    with urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))


def _discover_sport_keys(key: str) -> List[str]:
    """World-Cup soccer sport keys currently offered (sports listing is free)."""
    url = f"{API_BASE}/sports/?" + urlencode({"apiKey": key})
    try:
        sports = _http_json(url)
    except Exception:
        return [DEFAULT_SPORT]
    keys = [s.get("key") for s in sports
            if isinstance(s, dict) and isinstance(s.get("key"), str)]
    wc = [k for k in keys if k.startswith("soccer") and "world_cup" in k
          and "women" not in k and "qualif" not in k]
    return wc or [DEFAULT_SPORT]


def _median(values: List[float]) -> Optional[float]:
    vals = sorted(v for v in values if isinstance(v, (int, float)) and v > 1.0)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def _consensus_odds(event: Dict) -> Optional[List[float]]:
    """Median [home, draw, away] decimal odds for the EVENT's own home/away."""
    home, away = event.get("home_team"), event.get("away_team")
    h, d, a = [], [], []
    for bk in event.get("bookmakers", []):
        for mk in bk.get("markets", []):
            if mk.get("key") != "h2h":
                continue
            prices = {o.get("name"): o.get("price") for o in mk.get("outcomes", [])}
            if home in prices:
                h.append(prices[home])
            if away in prices:
                a.append(prices[away])
            if "Draw" in prices:
                d.append(prices["Draw"])
    mh, md, ma = _median(h), _median(d), _median(a)
    if mh and md and ma:
        return [round(mh, 2), round(md, 2), round(ma, 2)]
    return None


def events_to_board(events: List[Dict], ratings_payload: Dict,
                    fixtures_payload: Dict) -> Tuple[Dict[str, List[float]], int, int]:
    """Pure mapping (no network): API events -> {fixture_id: [home,draw,away]}.

    Returns (board, matched, unmatched). Odds are re-oriented to the fixture's
    home/away order. Only upcoming fixtures (no final score) are considered."""
    fx_index: Dict[frozenset, Dict] = {}
    for m in fixtures_payload.get("matches", []):
        if m.get("actual_home") is not None and m.get("actual_away") is not None:
            continue
        home, away = m.get("home"), m.get("away")
        if home and away:
            fx_index[frozenset((home.lower(), away.lower()))] = m

    board: Dict[str, List[float]] = {}
    matched = unmatched = 0
    for ev in events:
        odds = _consensus_odds(ev)
        if not odds:
            continue
        ch = data.resolve_team(ev.get("home_team", ""), ratings_payload)
        ca = data.resolve_team(ev.get("away_team", ""), ratings_payload)
        if not (ch and ca):
            unmatched += 1
            continue
        m = fx_index.get(frozenset((ch.lower(), ca.lower())))
        if not m:
            unmatched += 1
            continue
        # Re-orient: _consensus_odds is in the event's order; align to fixture.
        if ch.lower() == m["home"].lower():
            oriented = odds
        else:
            oriented = [odds[2], odds[1], odds[0]]
        fid = str(m.get("id") or "").upper() or f"{m['home']} vs {m['away']}"
        board[fid] = oriented
        matched += 1
    return board, matched, unmatched


def fetch_events(key: str) -> Tuple[List[Dict], List[str]]:
    events: List[Dict] = []
    errors: List[str] = []
    for sk in _discover_sport_keys(key):
        url = f"{API_BASE}/sports/{sk}/odds/?" + urlencode({
            "apiKey": key, "regions": REGIONS, "markets": MARKETS,
            "oddsFormat": "decimal",
        })
        try:
            payload = _http_json(url)
            if isinstance(payload, list):
                events.extend(payload)
        except HTTPError as e:
            errors.append(f"odds_http_{e.code}_{sk}")
        except Exception as e:  # network / parse — best effort
            errors.append(f"odds_fetch_{sk}_{type(e).__name__}")
    return events, errors


def build_board(ratings_payload: Dict, fixtures_payload: Dict) -> Tuple[Dict[str, List[float]], Dict]:
    report = {"fetched": 0, "matched": 0, "unmatched": 0, "skipped": "", "errors": []}
    key = get_key()
    if not key:
        report["skipped"] = "no_api_key"
        return {}, report
    events, errors = fetch_events(key)
    report["fetched"] = len(events)
    report["errors"].extend(errors)
    board, matched, unmatched = events_to_board(events, ratings_payload, fixtures_payload)
    report["matched"] = matched
    report["unmatched"] = unmatched
    return board, report


def write_board(board: Dict[str, List[float]], report: Optional[Dict] = None) -> None:
    with open(ODDS_PATH, "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=2)
        f.write("\n")
    state = {
        "fetched_at": _iso_now(),
        "source": "The Odds API (median EU bookmakers, h2h)",
        "matches": len(board),
    }
    if report:
        state["events_seen"] = report.get("fetched", 0)
        state["unmatched"] = report.get("unmatched", 0)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_state() -> Dict:
    if not STATE_PATH.is_file():
        return {}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
