"""Competition state ('stakes') for a group fixture: is each side already
QUALIFIED (top-2 secured), ELIMINATED, or still in CONTENTION — and the bounded
motivation adjustment that follows.

Why this exists: the Elo/Poisson model rates *strength*, never *situation*. An
already-qualified side rotates and an eliminated side has nothing to play for, so
their rating overstates what they'll actually do in a final-round dead rubber.
The market prices this; the model didn't — which is exactly how it kept flagging
"value" on teams the table had already settled.

Grounded in history, not a guess. Measured on the WC2022 group finale (32
team-performances), classifying each side's stakes going into matchday 3 and
comparing the result to the model's Elo expectation:

    going into the final round       Δ points/match vs Elo
    --------------------------       ---------------------
    already QUALIFIED (rotates)            -1.68   (1 win / 4)   <- biggest effect
    ELIMINATED (baroud d'honneur)          -0.62   (0 wins / 3)
    in CONTENTION (must-win)               +0.44   (+19% win rate)

Consistent with the qualitative record (France 2022 made 9 changes after
qualifying and lost to Tunisia; Brazil/Nigeria 1998 and Italy Euro 2016 topped
their group then lost the dead rubber; 2018 Russia 0-3, England 0-1). The
counter-intuitive part — confirmed above — is that the *qualified* side that
rests underperforms MORE than the *eliminated* side that still has pride to play
for. So we put a bounded Elo malus on the stakeless side(s); the contention side
keeps its true rating (its edge emerges from the opponent's malus).

Magnitudes are deliberately ~half the raw Elo-equivalent of the observed points
swing (small sample, high variance) and are tunable. They only ever move the
*displayed* prediction and the betting guard for UPCOMING group fixtures — the
status is recomputed from the live table, never frozen onto played matches, so
the backtest/solidity path is untouched.
"""
from __future__ import annotations

from itertools import product
from typing import Dict, List, Optional, Tuple

# Motivation malus (Elo points), applied to a stakeless side's rating. See the
# module docstring for the WC2022 measurement these are scaled from.
QUALIFIED_MALUS = -85.0    # guaranteed top 2 -> rotates ("dead rubber")
ELIMINATED_MALUS = -45.0   # cannot qualify -> reduced stakes (partly offset by pride)
THIRD_PLACE_BAR = 4        # max achievable points below which the best-third route
                           # is treated as hopeless (8 of 12 thirds advance in 2026;
                           # a side maxing at <=3 pts and out of the top 2 is gone)

QUALIFIED = "qualified"
ELIMINATED = "eliminated"
CONTENTION = "contention"

_MALUS = {QUALIFIED: QUALIFIED_MALUS, ELIMINATED: ELIMINATED_MALUS, CONTENTION: 0.0}
_LABELS = {QUALIFIED: "Qualifiée (top 2)", ELIMINATED: "Éliminée", CONTENTION: "En lice"}


def _is_completed(match: Dict) -> bool:
    return match.get("actual_home") is not None and match.get("actual_away") is not None


def _group_matches(group: str, fixtures: List[Dict]) -> List[Dict]:
    return [m for m in fixtures if str(m.get("stage") or "group") == "group"
            and m.get("group") == group]


def group_table(group: str, fixtures: List[Dict]) -> Tuple[Dict[str, Dict], List[Tuple[str, str]]]:
    """Current points/goal-difference table for a group + its unplayed fixtures.

    Returns ``(teams, remaining)`` where ``teams[name] = {pts, gf, ga, gd, played}``
    and ``remaining`` is the list of ``(home, away)`` games not yet played.
    """
    teams: Dict[str, Dict] = {}
    remaining: List[Tuple[str, str]] = []

    def ensure(t: str) -> None:
        teams.setdefault(t, {"pts": 0, "gf": 0, "ga": 0, "played": 0})

    for m in _group_matches(group, fixtures):
        h, a = m.get("home"), m.get("away")
        if not h or not a:
            continue
        ensure(h)
        ensure(a)
        gh, ga = m.get("actual_home"), m.get("actual_away")
        if gh is None or ga is None:
            remaining.append((h, a))
            continue
        teams[h]["played"] += 1
        teams[a]["played"] += 1
        teams[h]["gf"] += gh
        teams[h]["ga"] += ga
        teams[a]["gf"] += ga
        teams[a]["ga"] += gh
        if gh > ga:
            teams[h]["pts"] += 3
        elif gh < ga:
            teams[a]["pts"] += 3
        else:
            teams[h]["pts"] += 1
            teams[a]["pts"] += 1
    for row in teams.values():
        row["gd"] = row["gf"] - row["ga"]
    return teams, remaining


def team_status(team: str, group: str, fixtures: List[Dict],
                third_bar: int = THIRD_PLACE_BAR) -> str:
    """Classify a team's stakes: ``qualified`` / ``eliminated`` / ``contention``.

    Brute-forces every outcome of the group's remaining games (<=81 combos) and
    ranks each resulting table by (points, goal difference). A team is:
      * ``qualified``  — finishes top 2 in EVERY scenario (guaranteed through);
      * ``eliminated`` — finishes outside the top 2 in EVERY scenario AND can't
        reach ``third_bar`` points (so the best-third route is hopeless too);
      * ``contention`` — anything in between (the result still matters).

    Goal difference in unplayed games is modelled coarsely (±1 per decisive game)
    on top of the real current GD; the classification is points-driven, so this
    only sways pure tie-breaks, and ties are resolved conservatively (a team is
    never labelled eliminated/qualified on a GD knife-edge).
    """
    teams, remaining = group_table(group, fixtures)
    if team not in teams:
        return CONTENTION
    names = list(teams)

    ever_top2 = False
    never_top2 = True
    always_top2 = True
    best_pts = teams[team]["pts"]

    for combo in product((0, 1, 2), repeat=len(remaining)):
        pts = {t: teams[t]["pts"] for t in names}
        gd = {t: teams[t]["gd"] for t in names}
        for (h, a), r in zip(remaining, combo):
            if r == 0:
                pts[h] += 3
                gd[h] += 1
                gd[a] -= 1
            elif r == 2:
                pts[a] += 3
                gd[a] += 1
                gd[h] -= 1
            else:
                pts[h] += 1
                pts[a] += 1
        rank = sorted(names, key=lambda t: (-pts[t], -gd[t]))
        top2 = team in rank[:2]
        ever_top2 = ever_top2 or top2
        never_top2 = never_top2 and not top2
        always_top2 = always_top2 and top2
        if pts[team] > best_pts:
            best_pts = pts[team]

    if always_top2:
        return QUALIFIED
    if never_top2 and best_pts < third_bar:
        return ELIMINATED
    return CONTENTION


def stakes_for(match: Dict, fixtures: List[Dict]) -> Dict[str, object]:
    """Stakes + motivation deltas for one upcoming group fixture.

    Returns ``{delta_home, delta_away, status_home, status_away, label_home,
    label_away, dead_rubber}``. A *dead rubber* = both sides stakeless (neither
    qualified-and-rotating nor eliminated has anything to play for). For completed
    matches, non-group stages, or when neither side is settled, the deltas are 0
    so the model output is unchanged.
    """
    none = {
        "delta_home": 0.0, "delta_away": 0.0,
        "status_home": CONTENTION, "status_away": CONTENTION,
        "label_home": None, "label_away": None, "dead_rubber": False,
    }
    if _is_completed(match) or str(match.get("stage") or "group") != "group":
        return none
    group = match.get("group")
    home, away = match.get("home"), match.get("away")
    if not (group and home and away):
        return none

    sh = team_status(home, group, fixtures)
    sa = team_status(away, group, fixtures)
    dh, da = _MALUS[sh], _MALUS[sa]
    if dh == 0.0 and da == 0.0:
        return none
    return {
        "delta_home": dh,
        "delta_away": da,
        "status_home": sh,
        "status_away": sa,
        "label_home": _LABELS[sh] if dh else None,
        "label_away": _LABELS[sa] if da else None,
        "dead_rubber": sh != CONTENTION and sa != CONTENTION,
    }


def apply_stakes(ratings: Dict, match: Dict, fixtures: List[Dict]) -> Tuple[Dict, Dict]:
    """Return ``(ratings_for_match, stakes)``: a view of ``ratings`` with the two
    sides' Elo nudged by their motivation malus for THIS fixture, plus the raw
    stakes dict. When there's no adjustment the input ratings are returned as-is
    (no copy), so the common case stays cheap and byte-identical.
    """
    stakes = stakes_for(match, fixtures)
    dh, da = stakes["delta_home"], stakes["delta_away"]
    if not dh and not da:
        return ratings, stakes
    home, away = match.get("home"), match.get("away")
    teams = ratings.get("teams", {})
    if home not in teams or away not in teams:
        return ratings, stakes
    adj = dict(ratings)
    adj_teams = dict(teams)
    for name, delta in ((home, dh), (away, da)):
        if delta:
            row = dict(adj_teams[name])
            row["rating"] = float(row.get("rating", 0.0)) + delta
            row["stakes_delta"] = delta
            adj_teams[name] = row
    adj["teams"] = adj_teams
    return adj, stakes
