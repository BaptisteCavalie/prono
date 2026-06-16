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
2. The scoreline maximises expected Mon Petit Prono points. Base points come
   from the real MPP barème when known (``mpp_board``), else from the
   **committed/cached** bookmaker odds (``odds_board`` — ``data/odds.json`` /
   the odds cache), mapped ≈ cote×10. Using the *committed* board (never a live
   per-render fetch) keeps freeze and live identical: both read the same file,
   so the pick only moves when the committed odds are deliberately refreshed,
   not on every page load. Live odds-chasing stays on the Paris tab.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from engine import common, model, mpp


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


def scoreline(match: Dict, ratings: Dict,
              mpp_board: Optional[Dict] = None,
              odds_board: Optional[Dict] = None) -> Optional[Tuple[int, int]]:
    """Return the MPP-points-optimal ``(home, away)`` scoreline for one fixture,
    or ``None`` if a team is missing. Deterministic given the prepared ratings +
    the committed boards — this is exactly what gets displayed and frozen, so
    freeze and live can't drift. Knockout fixtures are optimised on the
    120-minute distribution (MPP counts extra time).

    Base-points source, by fidelity (the whole tool exists to win Mon Petit
    Prono, where points follow the cote — a correct draw pays ~2× a short
    favourite, so the pick must value the cote, not just the modal score):

    * ``mpp_board`` (``{FIXTURE_ID: [pts_home, pts_draw, pts_away]}``) — the
      *real* MPP barème when dictated (ask-Claude layer, ``data.load_mpp_board``).
    * ``odds_board`` (``{key: [home, draw, away]}`` decimals) — the
      **committed/cached** bookmaker odds as a proxy (``≈ cote×10``). Must be the
      committed board, not a live fetch, or the frozen pick would never match a
      re-render (cf. module docstring).

    Without either for this fixture it falls back to the model-only modal pick.
    """
    out = analyse_match(match, ratings)
    if out is None:
        return None
    mpp_points = (mpp_board or {}).get(str(match.get("id", "")).upper())
    odds = common.find_match_odds(match, odds_board) if odds_board else None
    ph, pa = mpp.recommend(out, odds=odds, mpp_points=mpp_points,
                           knockout=mpp.is_knockout(match))["score"]
    return int(ph), int(pa)
