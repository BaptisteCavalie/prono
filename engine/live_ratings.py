"""Keep Elo fresh as games are played — even on read-only hosts (Vercel).

Locally, autonomous_refresh already rewrites data/ratings.json, so this is a
no-op there. On a read-only host that refresh is skipped and ratings.json is
frozen at deploy time, so the bet list would never move after a result. This
module overlays the latest eloratings.net values onto the in-memory ratings on a
cooldown, caching the fetched map to the system temp dir. eloratings TSV is free
(no key, no quota), so the only cost is a little latency on a cold instance.

Never raises: on any failure it falls back to the cached map, then to whatever
ratings were passed in.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

from engine import autonomous, data

CACHE = Path(tempfile.gettempdir()) / "prono_elo_cache.json"
COOLDOWN_MIN = 180


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fresh(ts, cooldown_min: int) -> bool:
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() / 60.0 < cooldown_min


def _read_cache() -> Dict:
    if not CACHE.is_file():
        return {}
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(payload: Dict) -> None:
    try:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except OSError:
        pass


def _apply(ratings_payload: Dict, canon_map: Dict[str, int], as_of) -> int:
    teams = ratings_payload.get("teams", {})
    applied = 0
    for name, rating in (canon_map or {}).items():
        if name in teams:
            teams[name]["rating"] = int(rating)
            teams[name]["source"] = "live"
            applied += 1
    if as_of:
        ratings_payload["as_of"] = as_of
    return applied


def ensure(ratings_payload: Dict, cooldown_min: int = COOLDOWN_MIN,
           force: bool = False) -> Tuple[Dict, Dict]:
    """Overlay fresh Elo onto ratings_payload (in place) and return it + a report."""
    # Local / writable host: autonomous_refresh keeps ratings.json current already.
    if autonomous._data_dir_writable():
        return ratings_payload, {"used": "autonomous"}

    state = _read_cache()
    if not force and _fresh(state.get("fetched_at"), cooldown_min):
        n = _apply(ratings_payload, state.get("ratings", {}), state.get("as_of"))
        return ratings_payload, {"used": "cache", "applied": n, "as_of": state.get("as_of")}

    try:
        names = autonomous._parse_team_names()
        rmap = autonomous._parse_world_ratings()
        as_of = autonomous._parse_latest_as_of()
        canon: Dict[str, int] = {}
        for code, rating in rmap.items():
            nm = names.get(code)
            if not nm:
                continue
            c = data.resolve_team(nm, ratings_payload)
            if c:
                canon[c] = int(rating)
        n = _apply(ratings_payload, canon, as_of)
        _write_cache({"ratings": canon, "as_of": as_of, "fetched_at": _iso_now()})
        return ratings_payload, {"used": "live", "applied": n, "as_of": as_of}
    except Exception as exc:  # network/parse — fall back to cache, then base
        n = _apply(ratings_payload, state.get("ratings", {}), state.get("as_of"))
        return ratings_payload, {"used": "cache_fallback", "applied": n, "error": str(exc)}
