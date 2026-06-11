"""Expert priors: a trusted human forecaster's calls -> bounded rating nudge.

This is the same idea as engine/team_signals.py (form/injuries/news -> Elo
delta), but for *expert opinion* rather than team status. A pundit like Wiloo
has no crystal ball, so we treat his calls as a small, bounded, auditable prior
on top of the statistical model — never an override.

Each expert source is one JSON file in data/expert_sources/*.json:

    {
      "source": "wiloo",
      "label": "Wiloo — preview CDM 2026 (YouTube)",
      "video_url": "...",
      "captured_at": "2026-06-09",
      "trust": 1.0,            # global credibility dial for this source [0..1]
      "cap_elo": 35.0,         # max |delta| this source can move a rating
      "teams": {
        "Morocco": {
          "lean": 2,           # -2..+2: how far above/below its Elo he sees them
          "confidence": 0.8,   # 0..1: how convinced he is
          "stage_call": "1/2 finale",   # free text, audit only
          "quote": "...",                # free text, audit only
          "timestamp": "12:30"           # free text, audit only
        }
      },
      "outrights": {           # logged for post-hoc scoring of the expert
        "winner": "France",
        "finalists": ["France", "Brazil"],
        "dark_horses": ["Morocco"],
        "disappointments": ["Germany"]
      }
    }

delta_for_team = clamp(lean/2 * confidence * trust * cap_elo, -cap_elo, +cap_elo)

So at maximum conviction (lean=+/-2, confidence=1, trust=1) one source moves a
team by exactly +/-cap_elo. The sum across sources is clamped to GLOBAL_CAP_ELO.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

EXPERT_DIR = Path(__file__).resolve().parent.parent / "data" / "expert_sources"

DEFAULT_CAP_ELO = 35.0   # "nudge léger" — an expert refines, never overturns
GLOBAL_CAP_ELO = 60.0    # hard ceiling on the combined expert delta


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def load_sources(data_dir: Optional[Path] = None) -> List[Dict]:
    """Read every expert JSON file. Files whose name starts with '_' are docs."""
    directory = Path(data_dir) if data_dir else EXPERT_DIR
    if not directory.is_dir():
        return []
    out: List[Dict] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                out.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue  # a malformed expert file must never break predictions
    return out


def _source_team_delta(entry: Dict, trust: float, cap: float) -> float:
    lean = _clamp(float(entry.get("lean", 0.0) or 0.0), -2.0, 2.0)
    confidence = _clamp(float(entry.get("confidence", 0.0) or 0.0), 0.0, 1.0)
    raw = (lean / 2.0) * confidence * trust * cap
    return _clamp(raw, -cap, cap)


def team_delta(team: str, sources: List[Dict]) -> float:
    """Combined expert Elo delta for one team across all sources (bounded)."""
    total = 0.0
    for src in sources or []:
        entry = (src.get("teams") or {}).get(team)
        if not entry:
            continue
        trust = _clamp(float(src.get("trust", 1.0) or 0.0), 0.0, 1.0)
        cap = float(src.get("cap_elo", DEFAULT_CAP_ELO) or DEFAULT_CAP_ELO)
        total += _source_team_delta(entry, trust, cap)
    return _clamp(round(total, 2), -GLOBAL_CAP_ELO, GLOBAL_CAP_ELO)


def expert_notes(team: str, sources: List[Dict]) -> Iterable[str]:
    """Human-readable audit notes (who said what) for the prediction card."""
    notes: List[str] = []
    for src in sources or []:
        entry = (src.get("teams") or {}).get(team)
        if not entry:
            continue
        label = src.get("label") or src.get("source") or "expert"
        bits = []
        if entry.get("stage_call"):
            bits.append(str(entry["stage_call"]))
        if entry.get("quote"):
            bits.append(f"« {entry['quote']} »")
        detail = " — ".join(bits) if bits else f"lean {entry.get('lean', 0)}"
        notes.append(f"{label} sur {team} : {detail}")
    return notes


def apply_expert_priors(ratings: Dict, sources: Optional[List[Dict]] = None,
                        data_dir: Optional[Path] = None) -> Dict:
    """Fold expert priors into team ratings (no-op when no sources exist).

    Adds `expert_delta` per team and rolls it into `rating`, on top of any
    status_delta already applied. Returns a deep copy; the input is untouched.
    """
    if sources is None:
        sources = load_sources(data_dir)
    out = copy.deepcopy(ratings)
    teams = out.get("teams", {})
    for team, row in teams.items():
        delta = team_delta(team, sources)
        row["expert_delta"] = delta
        if delta:
            row["rating"] = round(float(row.get("rating", 0.0)) + delta, 2)
    return out
