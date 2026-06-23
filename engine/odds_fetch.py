"""Auto-fetch 1X2 (h2h) odds from The Odds API -> a cached odds board.

Free tier, one-time free key (https://the-odds-api.com). Key is read from, in
order: env ODDS_API_KEY, env odds_api_key, file data/odds_api_key.txt.

Credit discipline (the free plan is ~500 requests/month):
  * Only the Paris betting page calls ensure_board(); other pages read the cache.
  * ensure_board() re-fetches at most once per COOLDOWN_MIN (default 6h).
  * The Odds API returns x-requests-remaining; once that drops below MIN_CREDITS
    we stop fetching and serve the cache. Each fetch costs 1 credit (1 region x
    1 market); the sports-list lookup is free.
Each function degrades cleanly: no key / offline / out of season -> return the
cached board (possibly empty), never raise.

Cache location is writable-aware: data/ locally, the system temp dir on a
read-only host (Vercel/Lambda), so it works in both places.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from engine import data

try:                                            # exact Europe/Paris incl. DST
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:                               # no tz database -> WC is summer (CEST = UTC+2)
    _PARIS = timezone(timedelta(hours=2))

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
KEY_FILE = DATA_DIR / "odds_api_key.txt"

API_BASE = "https://api.the-odds-api.com/v4"
DEFAULT_SPORT = "soccer_fifa_world_cup"
REGIONS = "eu"
MARKETS = "h2h"

COOLDOWN_MIN = 360      # re-fetch at most every 6h
MIN_CREDITS = 20        # stop fetching once the plan is nearly exhausted


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_int(v) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def get_key() -> str:
    for env in ("ODDS_API_KEY", "odds_api_key"):
        v = (os.environ.get(env) or "").strip()
        if v:
            return v
    if KEY_FILE.is_file():
        try:
            return KEY_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def has_key() -> bool:
    return bool(get_key())


def _writable_data() -> bool:
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return False
    try:
        return os.access(DATA_DIR, os.W_OK)
    except OSError:
        return False


def _cache_paths() -> Tuple[Path, Path]:
    if _writable_data():
        return DATA_DIR / "odds.json", DATA_DIR / ".odds_state.json"
    tmp = Path(tempfile.gettempdir())
    return tmp / "prono_odds.json", tmp / "prono_odds_state.json"


def _kick_path() -> Path:
    if _writable_data():
        return DATA_DIR / "kickoffs.json"
    return Path(tempfile.gettempdir()) / "prono_kickoffs.json"


def paris_parts(utc_iso: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """UTC ISO kickoff -> (Paris date 'YYYY-MM-DD', Paris time 'HH:MM').

    This is the jetlag fix: a 21:00 US-evening kickoff is ~03:00 next-day in
    France, so it correctly rolls onto the next calendar date."""
    if not utc_iso:
        return None, None
    try:
        dt = datetime.fromisoformat(str(utc_iso).replace("Z", "+00:00"))
    except ValueError:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(_PARIS)
    return local.date().isoformat(), local.strftime("%H:%M")


def load_kickoffs() -> Dict[str, str]:
    """{FIXTURE_ID: utc_iso} captured from the odds feed (cache-only, no network)."""
    for p in (_kick_path(), DATA_DIR / "kickoffs.json"):
        if p.is_file():
            try:
                with open(p, encoding="utf-8") as f:
                    raw = json.load(f)
                return {str(k).upper(): v for k, v in raw.items() if isinstance(v, str)}
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def _http(url: str, timeout: int = 20):
    resp = urlopen(url, timeout=timeout)
    payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    return payload, resp.headers


def _norm_board(raw: Dict) -> Dict[str, List[float]]:
    board: Dict[str, List[float]] = {}
    for k, v in (raw or {}).items():
        if not (isinstance(v, list) and len(v) == 3):
            continue
        try:
            triple = [float(x) for x in v]
        except (TypeError, ValueError):
            continue
        pair = None
        for sep in (" vs ", " VS ", " v ", " - ", "/"):
            if sep in k:
                pair = k.split(sep, 1)
                break
        if pair:
            board[f"{pair[0].strip().lower()}|{pair[1].strip().lower()}"] = triple
        else:
            board[k.upper()] = triple
    return board


def _read_board(path: Path) -> Dict[str, List[float]]:
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return _norm_board(json.load(f))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_json(path: Path, payload) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_cached_board() -> Dict[str, List[float]]:
    """Read odds from cache only (no network). Prefers the live cache, then any
    committed data/odds.json."""
    cache_path, _ = _cache_paths()
    for p in (cache_path, DATA_DIR / "odds.json"):
        board = _read_board(p)
        if board:
            return board
    return {}


def read_state() -> Dict:
    _, state_path = _cache_paths()
    if not state_path.is_file():
        return {}
    try:
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _fresh(ts: Optional[str], cooldown_min: int) -> bool:
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    age_min = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
    return age_min < cooldown_min


def _median(values: List[float]) -> Optional[float]:
    vals = sorted(v for v in values if isinstance(v, (int, float)) and v > 1.0)
    n = len(vals)
    if n == 0:
        return None
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def _consensus_odds(event: Dict) -> Optional[List[float]]:
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
                    fixtures: List[Dict]) -> Tuple[Dict[str, List[float]], Dict[str, str], int, int]:
    """Pure mapping (no network): API events -> (board, kickoffs, matched, unmatched).

    board = {fixture_id: [home,draw,away]} (re-oriented to the fixture's order);
    kickoffs = {fixture_id: commence_time_utc}. Upcoming fixtures only."""
    fx_index: Dict[frozenset, Dict] = {}
    for m in fixtures or []:
        if m.get("actual_home") is not None and m.get("actual_away") is not None:
            continue
        home, away = m.get("home"), m.get("away")
        if home and away:
            fx_index[frozenset((home.lower(), away.lower()))] = m

    board: Dict[str, List[float]] = {}
    kickoffs: Dict[str, str] = {}
    matched = unmatched = 0
    for ev in events or []:
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
        oriented = odds if ch.lower() == m["home"].lower() else [odds[2], odds[1], odds[0]]
        fid = str(m.get("id") or "").upper() or f"{m['home']} vs {m['away']}"
        board[fid] = oriented
        ct = ev.get("commence_time")
        if isinstance(ct, str) and ct:
            kickoffs[fid] = ct
        matched += 1
    return board, kickoffs, matched, unmatched


def _discover_sport_key(key: str) -> str:
    url = f"{API_BASE}/sports/?" + urlencode({"apiKey": key})   # free, no quota
    try:
        sports, _ = _http(url)
    except Exception:
        return DEFAULT_SPORT
    keys = [s.get("key") for s in sports
            if isinstance(s, dict) and isinstance(s.get("key"), str)]
    wc = [k for k in keys if k.startswith("soccer") and "world_cup" in k
          and "women" not in k and "qualif" not in k]
    return wc[0] if wc else DEFAULT_SPORT


def fetch_events(key: str):
    """Return (events, remaining_credits, used_credits, errors, sport_key)."""
    errors: List[str] = []
    sk = _discover_sport_key(key)
    url = f"{API_BASE}/sports/{sk}/odds/?" + urlencode({
        "apiKey": key, "regions": REGIONS, "markets": MARKETS, "oddsFormat": "decimal",
    })
    try:
        payload, headers = _http(url)
        remaining = _to_int(headers.get("x-requests-remaining"))
        used = _to_int(headers.get("x-requests-used"))
        events = payload if isinstance(payload, list) else []
        return events, remaining, used, errors, sk
    except HTTPError as e:
        errors.append(f"odds_http_{e.code}")
        remaining = None
        try:
            remaining = _to_int(e.headers.get("x-requests-remaining"))
        except Exception:
            pass
        return [], remaining, None, errors, sk
    except Exception as e:
        errors.append(f"odds_fetch_{type(e).__name__}")
        return [], None, None, errors, sk


# --- Outright / futures market (tournament winner) ---------------------------
# The Odds API serves tournament futures under a dedicated "*_winner" sport key
# with the `outrights` market: one event whose outcomes are {team: price}. That
# covers the CHAMPION market in prod; markets the API doesn't carry for soccer
# (group winner, reach-final) stay on the manual data/outrights.json overlay.
WINNER_MARKET = "outrights"
DEFAULT_WINNER_SPORT = "soccer_fifa_world_cup_winner"


def _outright_cache_paths() -> Tuple[Path, Path]:
    if _writable_data():
        return DATA_DIR / "outrights_cache.json", DATA_DIR / ".outrights_state.json"
    tmp = Path(tempfile.gettempdir())
    return tmp / "prono_outrights.json", tmp / "prono_outrights_state.json"


def _read_outright_board(path: Path) -> Dict:
    """Read a cached ``{"markets": {...}}`` outright board (no network)."""
    if not path.is_file():
        return {"markets": {}}
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) and isinstance(raw.get("markets"), dict) else {"markets": {}}
    except (OSError, json.JSONDecodeError):
        return {"markets": {}}


def load_cached_outrights() -> Dict:
    """Read auto-fetched outright odds from cache only (no network, no credits)."""
    cache_path, _ = _outright_cache_paths()
    return _read_outright_board(cache_path)


def read_outright_state() -> Dict:
    _, state_path = _outright_cache_paths()
    if not state_path.is_file():
        return {}
    try:
        with open(state_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _discover_winner_sport_key(key: str) -> str:
    url = f"{API_BASE}/sports/?" + urlencode({"apiKey": key})   # free, no quota
    try:
        sports, _ = _http(url)
    except Exception:
        return DEFAULT_WINNER_SPORT
    keys = [s.get("key") for s in sports
            if isinstance(s, dict) and isinstance(s.get("key"), str)]
    wc = [k for k in keys if k.startswith("soccer") and "world_cup" in k
          and "winner" in k and "women" not in k and "qualif" not in k]
    return wc[0] if wc else DEFAULT_WINNER_SPORT


def fetch_outright_events(key: str):
    """Return (events, remaining_credits, used_credits, errors, sport_key)."""
    errors: List[str] = []
    sk = _discover_winner_sport_key(key)
    url = f"{API_BASE}/sports/{sk}/odds/?" + urlencode({
        "apiKey": key, "regions": REGIONS, "markets": WINNER_MARKET, "oddsFormat": "decimal",
    })
    try:
        payload, headers = _http(url)
        remaining = _to_int(headers.get("x-requests-remaining"))
        used = _to_int(headers.get("x-requests-used"))
        events = payload if isinstance(payload, list) else []
        return events, remaining, used, errors, sk
    except HTTPError as e:
        errors.append(f"outrights_http_{e.code}")
        remaining = None
        try:
            remaining = _to_int(e.headers.get("x-requests-remaining"))
        except Exception:
            pass
        return [], remaining, None, errors, sk
    except Exception as e:
        errors.append(f"outrights_fetch_{type(e).__name__}")
        return [], None, None, errors, sk


def outright_events_to_market(events: List[Dict], ratings_payload: Dict) -> Dict[str, float]:
    """Pure mapping (no network): outright events -> {team: consensus_odds}.

    Median price per team across every bookmaker offering the `outrights` market,
    with team names resolved to the canonical ratings spelling (so the sim and
    the odds line up)."""
    prices: Dict[str, List[float]] = {}
    for ev in events or []:
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                if mk.get("key") != WINNER_MARKET:
                    continue
                for o in mk.get("outcomes", []):
                    price = o.get("price")
                    if not isinstance(price, (int, float)) or price <= 1.0:
                        continue
                    raw = (o.get("name") or "").strip()
                    team = data.resolve_team(raw, ratings_payload) or raw
                    if team:
                        prices.setdefault(team, []).append(float(price))
    market: Dict[str, float] = {}
    for team, vals in prices.items():
        med = _median(vals)
        if med:
            market[team] = round(med, 2)
    return market


def ensure_outrights(ratings_payload: Dict, cooldown_min: int = COOLDOWN_MIN,
                     force: bool = False) -> Dict:
    """Return the auto-fetched outright board ``{"markets": {"champion": {...}}}``,
    fetching at most once per cooldown and stopping when credits run low. Never
    raises; falls back to the cache. Same credit discipline as ``ensure_board``."""
    cache_path, state_path = _outright_cache_paths()
    state = read_outright_state()
    cached = _read_outright_board(cache_path)

    if not has_key():
        return cached

    rem = state.get("remaining_credits")
    if isinstance(rem, int) and rem < MIN_CREDITS and not force:
        return cached
    if not force and _fresh(state.get("attempted_at"), cooldown_min):
        return cached

    events, remaining, used, errors, sk = fetch_outright_events(get_key())
    market = outright_events_to_market(events, ratings_payload)
    board = {"markets": {"champion": market}} if market else {"markets": {}}

    new_state = {
        "attempted_at": _iso_now(),
        "source": "The Odds API (median EU bookmakers, outrights)",
        "sport_key": sk,
        "remaining_credits": remaining if remaining is not None else state.get("remaining_credits"),
        "used_credits": used if used is not None else state.get("used_credits"),
        "errors": errors,
    }
    try:
        if market:                                      # don't wipe good odds with an empty fetch
            new_state["fetched_at"] = new_state["attempted_at"]
            new_state["teams"] = len(market)
            _write_json(cache_path, board)
            _write_json(state_path, new_state)
            return board
        new_state["fetched_at"] = state.get("fetched_at")
        _write_json(state_path, new_state)              # record the attempt -> honour cooldown
    except OSError:
        pass
    return cached


def ensure_board(ratings_payload: Dict, fixtures: List[Dict],
                 cooldown_min: int = COOLDOWN_MIN, force: bool = False) -> Dict[str, List[float]]:
    """Return the odds board, fetching at most once per cooldown and stopping when
    credits run low. Never raises; falls back to the cache."""
    cache_path, state_path = _cache_paths()
    state = read_state()
    cached = _read_board(cache_path) or load_cached_board()

    if not has_key():
        return cached

    rem = state.get("remaining_credits")
    if isinstance(rem, int) and rem < MIN_CREDITS and not force:
        return cached                                   # protect the budget
    if not force and _fresh(state.get("attempted_at"), cooldown_min):
        return cached                                   # cooldown

    events, remaining, used, errors, sk = fetch_events(get_key())
    board, kickoffs, matched, unmatched = events_to_board(events, ratings_payload, fixtures)

    new_state = {
        "attempted_at": _iso_now(),
        "source": "The Odds API (median EU bookmakers, h2h)",
        "sport_key": sk,
        "remaining_credits": remaining if remaining is not None else state.get("remaining_credits"),
        "used_credits": used if used is not None else state.get("used_credits"),
        "unmatched": unmatched,
        "errors": errors,
    }
    try:
        if board:                                       # don't wipe good odds with an empty fetch
            new_state["fetched_at"] = new_state["attempted_at"]
            new_state["matches"] = len(board)
            _write_json(cache_path, board)
            _write_json(state_path, new_state)
            if kickoffs:
                _write_json(_kick_path(), kickoffs)     # persist kickoff times for the date fix
            return board
        new_state["fetched_at"] = state.get("fetched_at")
        new_state["matches"] = len(cached)
        _write_json(state_path, new_state)              # record the attempt -> honour cooldown
    except OSError:
        pass                                            # read-only edge: just serve cache
    return cached
