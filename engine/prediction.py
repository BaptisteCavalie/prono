"""Single source of truth for turning a fixture + ratings into a model output
and the displayed/frozen scoreline.

Every prono surface that shows or freezes a scoreline (the web calendar in
``ui.py``, the autonomous freeze in ``autonomous.py``, the manual snapshot tool
in ``tools/snapshot_predictions.py``) MUST go through here, so the displayed
prono, the frozen prono and any recompute stay identical by construction.

Two rules this module enforces, both of which were the source of real
"Prono mis a jour" phantom-update bugs when they were duplicated by hand:

1. The model is always called with the same inputs: team ratings + the
   per-team attack/defense rows + the fixture's home advantage.
2. The scoreline is model-only (no bookmaker odds). Odds move constantly and
   cannot be re-frozen on a read-only host, so an odds-driven scoreline would
   never match a frozen one. Odds-aware logic lives in ``engine.betting`` /
   the Paris tab, never in the calendar prono.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from engine import model, mpp


def analyse_match(match: Dict, ratings: Dict) -> Optional[Dict]:
    """Return ``model.analyse`` output for one fixture, or ``None`` if either
    team is missing from ``ratings``. ``ratings`` must already be prepared the
    way the UI prepares it (completed-result + team-signal adjustments applied);
    this function does not touch the ratings pipeline."""
    teams = ratings.get("teams", {})
    home = match.get("home")
    away = match.get("away")
    if home not in teams or away not in teams:
        return None
    rh = teams[home]
    ra = teams[away]
    return model.analyse(
        float(rh.get("rating", 0.0)),
        float(ra.get("rating", 0.0)),
        home_adv=float(match.get("home_adv", 0.0) or 0.0),
        ad_home=model.ad_from_row(rh),
        ad_away=model.ad_from_row(ra),
    )


def scoreline(match: Dict, ratings: Dict) -> Optional[Tuple[int, int]]:
    """Return the model-only MPP-optimal ``(home, away)`` scoreline for one
    fixture, or ``None`` if a team is missing. Deterministic given the prepared
    ratings — this is exactly what gets displayed and frozen. Knockout fixtures
    are optimised on the 120-minute distribution (MPP counts extra time)."""
    out = analyse_match(match, ratings)
    if out is None:
        return None
    ph, pa = mpp.recommend(out, knockout=mpp.is_knockout(match))["score"]
    return int(ph), int(pa)
