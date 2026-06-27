"""Forward tournament simulation: project the World Cup from the live group
tables all the way to the trophy.

Why this module exists
----------------------
The rest of the engine prices ONE match at a time (``engine/model.py`` +
``engine/prediction.py``). That is everything you need for a group-stage prono,
but it cannot answer the questions that actually win **Mon Petit Prono** and
**outright bets** once the knockouts loom:

  * who reaches the Round of 32 / 16 / quarters / semis / final, and with what
    probability — the 48-team / 12-group / best-8-thirds maths is not something
    you can eyeball;
  * what the knockout BRACKET will look like (FIFA's pre-planned R32 structure +
    the third-place allocation), so the MPP x2 and the per-round scorelines can
    be planned a round ahead;
  * each team's probability of WINNING the tournament / reaching the final /
    topping its group — the only honest basis for an outright value bet, because
    chaining single-match favourites systematically overstates a deep run
    (knockouts are ~2/3 favourite, see data/history.json).

How it works
------------
A Monte-Carlo over the *remaining* tournament. Each simulation:

  1. samples every unplayed group match from the SAME Dixon-Coles-corrected
     score matrix the rest of the app uses (``engine.prediction.analyse_match``),
     so the sim and the per-match prono can never disagree;
  2. builds the 12 final group tables (points → GD → GF → random tie-break),
     reads off the 12 winners, 12 runners-up and the 8 best third-placed teams;
  3. allocates the eight thirds to the eight R32 third-slots respecting FIFA's
     per-slot group eligibility (``data/bracket.json``);
  4. plays the bracket R32 → final as knockout ties: 90' from the score matrix,
     then a tempo-damped extra time, then a near-coin-flip shootout
     (``data/history.json``), tallying who reaches each round.

Group motivation (``engine/standings.py``) is applied to the remaining group
fixtures exactly as the displayed prono does, so an already-qualified side's
dead-rubber rotation is priced in. The knockout legs are neutral-venue except a
conservative host bonus when a host nation plays.

The output feeds three surfaces: the qualification / reach-round table, the
projected bracket (for MPP planning), and the outright probabilities
(``engine/outrights.py``). It is deterministic given ``seed``.
"""
from __future__ import annotations

import bisect
import math
import random
from typing import Dict, List, Optional, Tuple

from engine import (data, expert_signals, home_advantage, model, mpp,
                    prediction, standings, team_signals)

# Knockout extra-time / shootout model. ET reuses the MPP 120' constants so the
# advancement model and the MPP scoreline optimiser stay in lock-step; the
# shootout lean comes from the historical record (data/history.json).
ET_FRACTION = mpp.ET_FRACTION
ET_TEMPO = mpp.ET_TEMPO
SHOOTOUT_SKILL_LEAN = 0.20   # P(stronger wins pens) = .5 + lean*(win_exp-.5)
KO_HOST_ADV = home_advantage.HOST_HOME_ADV / 2.0  # hosts play KO at/near home

DEFAULT_SIMS = 20000
_ROUND_KEYS = ("r32", "r16", "qf", "sf", "final")


# --- match samplers ----------------------------------------------------------

def _cumulative(lam_h: float, lam_a: float) -> Tuple[List[Tuple[int, int]], List[float], float]:
    """Flatten the Dixon-Coles score matrix into (cells, cumulative, total) for
    O(log n) inverse-CDF sampling — identical distribution to model.analyse."""
    m = model.score_matrix(lam_h, lam_a)
    n = len(m)
    cells: List[Tuple[int, int]] = []
    cum: List[float] = []
    run = 0.0
    for i in range(n):
        for j in range(n):
            run += m[i][j]
            cells.append((i, j))
            cum.append(run)
    return cells, cum, run


def _sample(cells, cum, total, rng) -> Tuple[int, int]:
    return cells[bisect.bisect_left(cum, rng.random() * total)]


def _poisson_sample(lam: float, rng) -> int:
    """Knuth Poisson sampler (small lambdas in extra time)."""
    if lam <= 0:
        return 0
    el = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= el:
            return k
        k += 1


class _KnockoutModel:
    """Lazily-built, memoised knockout match sampler over prepared ratings."""

    def __init__(self, ratings: Dict):
        self._teams = ratings.get("teams", {})
        self._memo: Dict[Tuple[str, str], tuple] = {}

    def _params(self, home: str, away: str):
        key = (home, away)
        hit = self._memo.get(key)
        if hit is not None:
            return hit
        rh = self._teams.get(home, {})
        ra = self._teams.get(away, {})
        adv = 0.0
        if home_advantage.is_host(home) and not home_advantage.is_host(away):
            adv = KO_HOST_ADV
        elif home_advantage.is_host(away) and not home_advantage.is_host(home):
            adv = -KO_HOST_ADV
        lam_h, lam_a = model.expected_goals(
            float(rh.get("rating", 0.0)), float(ra.get("rating", 0.0)),
            home_adv=adv, ad_home=model.ad_from_row(rh), ad_away=model.ad_from_row(ra))
        cells, cum, total = _cumulative(lam_h, lam_a)
        we_home = model.win_expectancy(
            (float(rh.get("rating", 0.0)) + adv - float(ra.get("rating", 0.0)))
            * model.RATING_SHRINK)
        params = (cells, cum, total, lam_h, lam_a, we_home)
        self._memo[key] = params
        return params

    def play(self, home: str, away: str, rng, tally: Optional[Dict] = None) -> str:
        """Return the winner of a knockout tie (90' → ET → pens)."""
        cells, cum, total, lam_h, lam_a, we_home = self._params(home, away)
        i, j = _sample(cells, cum, total, rng)
        if tally is not None:
            tally["ko_matches"] += 1
            tally["goals"] += i + j          # 90' goals — the comparable, well
                                             # documented historical quantity
        if i > j:
            return home
        if i < j:
            return away
        # level after 90' → extra time (tempo-damped)
        if tally is not None:
            tally["et"] += 1
        dh = _poisson_sample(lam_h * ET_FRACTION * ET_TEMPO, rng)
        da = _poisson_sample(lam_a * ET_FRACTION * ET_TEMPO, rng)
        if tally is not None:
            tally["et_goals"] += dh + da
        if dh > da:
            return home
        if dh < da:
            return away
        # still level → penalty shootout (near coin-flip, slight skill lean)
        if tally is not None:
            tally["pens"] += 1
        p_home = 0.5 + SHOOTOUT_SKILL_LEAN * (we_home - 0.5)
        return home if rng.random() < p_home else away


def _poisson_win_probs(lam_h: float, lam_a: float, max_goals: int = 12):
    """Analytic P(home wins), P(level), P(away wins) for two independent
    Poisson scorers — used for the (low-scoring) extra-time period, which the
    sim draws from plain Poisson (no Dixon-Coles), so this matches ``play``."""
    ph = [model.poisson_pmf(k, lam_h) for k in range(max_goals + 1)]
    pa = [model.poisson_pmf(k, lam_a) for k in range(max_goals + 1)]
    p_home = p_draw = p_away = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[i] * pa[j]
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    return p_home, p_draw, p_away


def advance_prob(home: str, away: str, ratings: Dict) -> Optional[float]:
    """Analytic P(``home`` advances) in a knockout tie, or ``None`` if a rating
    is missing. The exact closed form of ``_KnockoutModel.play``:

        P(adv) = P(win 90') + P(draw 90') · [ P(win ET) + P(draw ET) · p_pens ]

    90' comes from the Dixon-Coles matrix the whole app uses, extra time from a
    tempo-damped Poisson, the shootout from the historical near-coin-flip with a
    slight skill lean. Same constants and host bonus as the Monte-Carlo, so the
    per-tie "who qualifies" price and the bracket sim can never disagree.
    """
    teams = ratings.get("teams", {})
    if home not in teams or away not in teams:
        return None
    rh, ra = teams[home], teams[away]
    adv = 0.0
    if home_advantage.is_host(home) and not home_advantage.is_host(away):
        adv = KO_HOST_ADV
    elif home_advantage.is_host(away) and not home_advantage.is_host(home):
        adv = -KO_HOST_ADV
    rate_h = float(rh.get("rating", 0.0))
    rate_a = float(ra.get("rating", 0.0))
    lam_h, lam_a = model.expected_goals(
        rate_h, rate_a, home_adv=adv,
        ad_home=model.ad_from_row(rh), ad_away=model.ad_from_row(ra))

    m = model.score_matrix(lam_h, lam_a)
    n = len(m)
    total = sum(m[i][j] for i in range(n) for j in range(n))
    p_home90 = sum(m[i][j] for i in range(n) for j in range(n) if i > j) / total
    p_draw90 = sum(m[i][i] for i in range(n)) / total

    et_h, et_a = lam_h * ET_FRACTION * ET_TEMPO, lam_a * ET_FRACTION * ET_TEMPO
    p_home_et, p_draw_et, _ = _poisson_win_probs(et_h, et_a)

    we_home = model.win_expectancy((rate_h + adv - rate_a) * model.RATING_SHRINK)
    p_pens_home = 0.5 + SHOOTOUT_SKILL_LEAN * (we_home - 0.5)

    return p_home90 + p_draw90 * (p_home_et + p_draw_et * p_pens_home)


# --- group stage -------------------------------------------------------------

def _base_table(group: str, members: List[str], fixtures: List[Dict]):
    """Points/GD/GF from already-played group matches + the unplayed fixtures."""
    table = {t: {"pts": 0, "gd": 0, "gf": 0} for t in members}
    remaining: List[Tuple[str, str]] = []
    for m in fixtures:
        if str(m.get("stage") or "group") != "group" or m.get("group") != group:
            continue
        h, a = m.get("home"), m.get("away")
        if h not in table or a not in table:
            continue
        gh, ga = m.get("actual_home"), m.get("actual_away")
        if gh is None or ga is None:
            remaining.append((h, a))
            continue
        table[h]["gf"] += gh
        table[h]["gd"] += gh - ga
        table[a]["gf"] += ga
        table[a]["gd"] += ga - gh
        if gh > ga:
            table[h]["pts"] += 3
        elif gh < ga:
            table[a]["pts"] += 3
        else:
            table[h]["pts"] += 1
            table[a]["pts"] += 1
    return table, remaining


def _remaining_samplers(group: str, remaining, ratings, fixtures):
    """One pre-built score sampler per unplayed group fixture (stakes applied),
    so the per-sim cost is a single inverse-CDF draw. Bookmaker odds are
    irrelevant here — they shape the MPP *scoreline*, never the model's outcome
    probabilities, which is what the simulation samples."""
    out = []
    by_pair = {}
    for m in fixtures:
        if str(m.get("stage") or "group") != "group" or m.get("group") != group:
            continue
        if m.get("actual_home") is None:
            by_pair[(m.get("home"), m.get("away"))] = m
    for (h, a) in remaining:
        fx = by_pair.get((h, a))
        if fx is None:
            continue
        adj_ratings, _ = standings.apply_stakes(ratings, fx, fixtures)
        an = prediction.analyse_match(fx, adj_ratings)
        if an is None:        # missing rating — skip (handled by caller)
            out.append((h, a, None))
            continue
        out.append((h, a, _cumulative(an["lambda_home"], an["lambda_away"])))
    return out


# --- third-place allocation --------------------------------------------------

def _allocate_thirds(third_slots, thirds_by_group, rng) -> Dict[int, str]:
    """Assign the 8 qualifying thirds to the 8 R32 third-slots respecting each
    slot's FIFA group eligibility. Backtracking, most-constrained slot first;
    returns {match_id: team}. Falls back to a relaxed fill if (impossibly) no
    eligibility-respecting matching exists."""
    groups_avail = set(thirds_by_group)
    slots = sorted(
        ({"m": s["m"], "elig": set(s["elig"]) & groups_avail} for s in third_slots),
        key=lambda s: len(s["elig"]))
    assignment: Dict[int, str] = {}
    used: set = set()

    def solve(k: int) -> bool:
        if k == len(slots):
            return True
        slot = slots[k]
        cands = [g for g in slot["elig"] if g not in used]
        rng.shuffle(cands)
        for g in cands:
            used.add(g)
            assignment[slot["m"]] = thirds_by_group[g]
            if solve(k + 1):
                return True
            used.discard(g)
            del assignment[slot["m"]]
        return False

    if solve(0):
        return assignment
    # Relaxed fallback (should never trigger for a real 8-of-12 subset).
    leftover = [thirds_by_group[g] for g in groups_avail]
    rng.shuffle(leftover)
    return {s["m"]: leftover[i] for i, s in enumerate(slots)}


# --- the simulation ----------------------------------------------------------

def _rank(table, members, rng):
    """Final group order: points → GD → GF → random tie-break."""
    jitter = {t: rng.random() for t in members}
    return sorted(members,
                  key=lambda t: (-table[t]["pts"], -table[t]["gd"],
                                 -table[t]["gf"], jitter[t]))


def _third_slots(bracket) -> List[Dict]:
    return [{"m": e["m"], "elig": e["b"]["t"]}
            for e in bracket["r32"] if "t" in e.get("b", {})]


def simulate(fixtures: List[Dict], ratings: Dict, groups: Dict, bracket: Dict,
             n_sims: int = DEFAULT_SIMS, seed: int = 12345) -> Dict:
    """Run the Monte-Carlo and return raw counts + per-team probabilities.

    ``ratings`` must already be prepared (team-status + expert priors applied) —
    the same view the UI/CLI predict with. ``groups`` is ``{letter: [teams]}``.
    """
    rng = random.Random(seed)
    km = _KnockoutModel(ratings)
    third_slots = _third_slots(bracket)

    # Pre-build group base tables + per-fixture samplers once.
    g_meta = {}
    for g, members in groups.items():
        table0, remaining = _base_table(g, members, fixtures)
        samplers = _remaining_samplers(g, remaining, ratings, fixtures)
        g_meta[g] = {"members": members, "table0": table0, "samplers": samplers}

    teams_all = [t for members in groups.values() for t in members]
    counts = {t: {k: 0 for k in ("first", "second", "third_qual", "qualify",
                                 "r16", "qf", "sf", "final", "champion")}
              for t in teams_all}
    calib = {"ko_matches": 0, "et": 0, "pens": 0, "goals": 0, "et_goals": 0}

    r32, r16, qf, sf, final = (bracket["r32"], bracket["r16"], bracket["qf"],
                               bracket["sf"], bracket["final"])

    for _ in range(n_sims):
        winners: Dict[str, str] = {}
        runners: Dict[str, str] = {}
        thirds_rows: List[Tuple[str, str, Dict]] = []  # (team, group, stats)

        for g, meta in g_meta.items():
            table = {t: dict(meta["table0"][t]) for t in meta["members"]}
            for (h, a, samp) in meta["samplers"]:
                if samp is None:
                    continue
                gh, ga = _sample(*samp, rng)
                table[h]["gf"] += gh
                table[h]["gd"] += gh - ga
                table[a]["gf"] += ga
                table[a]["gd"] += ga - gh
                if gh > ga:
                    table[h]["pts"] += 3
                elif gh < ga:
                    table[a]["pts"] += 3
                else:
                    table[h]["pts"] += 1
                    table[a]["pts"] += 1
            order = _rank(table, meta["members"], rng)
            winners[g] = order[0]
            runners[g] = order[1]
            counts[order[0]]["first"] += 1
            counts[order[1]]["second"] += 1
            thirds_rows.append((order[2], g, table[order[2]]))

        # Best 8 of the 12 third-placed teams.
        jitter = {row[0]: rng.random() for row in thirds_rows}
        thirds_rows.sort(key=lambda r: (-r[2]["pts"], -r[2]["gd"],
                                        -r[2]["gf"], jitter[r[0]]))
        qual_thirds = thirds_rows[:8]
        thirds_by_group = {g: team for (team, g, _stats) in qual_thirds}
        for (team, _g, _s) in qual_thirds:
            counts[team]["third_qual"] += 1
        third_assign = _allocate_thirds(third_slots, thirds_by_group, rng)

        # Everyone in the R32 has "qualified".
        for team in list(winners.values()) + list(runners.values()):
            counts[team]["qualify"] += 1
        for (team, _g, _s) in qual_thirds:
            counts[team]["qualify"] += 1

        # Resolve & play the bracket.
        def resolve(spec, match_id, results):
            if "w" in spec:
                return winners[spec["w"]]
            if "r" in spec:
                return runners[spec["r"]]
            if "t" in spec:
                return third_assign.get(match_id)
            return results[spec["win"]]

        results: Dict[int, str] = {}
        for entry in r32:
            h = resolve(entry["a"], entry["m"], results)
            a = resolve(entry["b"], entry["m"], results)
            results[entry["m"]] = km.play(h, a, rng, calib) if (h and a) else (h or a)

        for entry in r16:
            h = results[entry["a"]["win"]]
            a = results[entry["b"]["win"]]
            counts[h]["r16"] += 1
            counts[a]["r16"] += 1
            results[entry["m"]] = km.play(h, a, rng, calib)
        for entry in qf:
            h = results[entry["a"]["win"]]
            a = results[entry["b"]["win"]]
            counts[h]["qf"] += 1
            counts[a]["qf"] += 1
            results[entry["m"]] = km.play(h, a, rng, calib)
        for entry in sf:
            h = results[entry["a"]["win"]]
            a = results[entry["b"]["win"]]
            counts[h]["sf"] += 1
            counts[a]["sf"] += 1
            results[entry["m"]] = km.play(h, a, rng, calib)
        for entry in final:
            h = results[entry["a"]["win"]]
            a = results[entry["b"]["win"]]
            counts[h]["final"] += 1
            counts[a]["final"] += 1
            results[entry["m"]] = km.play(h, a, rng, calib)
        counts[results[final[0]["m"]]]["champion"] += 1

    n = float(n_sims)
    team_to_group = {t: g for g, members in groups.items() for t in members}
    probs = {}
    for t, c in counts.items():
        probs[t] = {
            "group": team_to_group.get(t),
            "p_first": c["first"] / n,
            "p_second": c["second"] / n,
            "p_third_qual": c["third_qual"] / n,
            "p_qualify": c["qualify"] / n,
            "p_r16": c["r16"] / n,
            "p_qf": c["qf"] / n,
            "p_sf": c["sf"] / n,
            "p_final": c["final"] / n,
            "p_champion": c["champion"] / n,
        }

    ko = max(1, calib["ko_matches"])
    calibration = {
        "ko_matches_per_sim": calib["ko_matches"] / n,
        "realized_et_share": calib["et"] / ko,
        "realized_pen_share": calib["pens"] / ko,
        "realized_goals_pg": calib["goals"] / ko,        # 90' only
        "realized_goals_pg_incl_et": (calib["goals"] + calib["et_goals"]) / ko,
    }
    return {"n_sims": n_sims, "teams": probs, "calibration": calibration}


# --- high-level entry points -------------------------------------------------

def prepare_ratings(fixtures: Optional[List[Dict]] = None) -> Dict:
    """Load and prepare ratings the way the rest of the app predicts with
    (team-status signals + expert priors). Loaded fresh so the sim never depends
    on a caller mutating a shared dict."""
    ratings = data.load_ratings()
    status = data.load_team_status()
    ratings = team_signals.adjust_ratings_with_status(ratings, status)
    ratings = expert_signals.apply_expert_priors(ratings)
    return ratings


def project(n_sims: int = DEFAULT_SIMS, seed: int = 12345,
            ratings: Optional[Dict] = None,
            fixtures: Optional[List[Dict]] = None) -> Dict:
    """End-to-end projection: load everything, run the sim, attach the projected
    (single most-likely) bracket and the calibration check. This is the one call
    the CLI and the UI use."""
    fixtures = fixtures if fixtures is not None else data.load_fixtures()
    ratings = ratings if ratings is not None else prepare_ratings(fixtures)
    groups = data.load_groups()
    bracket = data.load_bracket()

    sim = simulate(fixtures, ratings, groups, bracket, n_sims=n_sims, seed=seed)
    sim["projected_bracket"] = projected_bracket(sim, groups, bracket)
    sim["calibration"]["targets"] = data.load_history().get("knockout_base_rates", {})
    return sim


def projected_bracket(sim: Dict, groups: Dict, bracket: Dict) -> Dict:
    """The single most-likely qualifier set + resolved R32 card.

    A planning aid (clearly *one* scenario, not a forecast): per group the team
    most likely to finish 1st and the most likely 2nd, plus the eight most-likely
    qualifying thirds, allocated to slots. Lets MPP/x2 planning look a round ahead
    before the real bracket locks.
    """
    probs = sim["teams"]
    winners, runners = {}, {}
    for g, members in groups.items():
        ranked_first = sorted(members, key=lambda t: -probs[t]["p_first"])
        winners[g] = ranked_first[0]
        runners[g] = max((t for t in members if t != winners[g]),
                         key=lambda t: probs[t]["p_second"])
    # eight most-likely qualifying thirds (exclude projected 1st/2nd)
    taken = set(winners.values()) | set(runners.values())
    third_cands = sorted((t for t in probs if t not in taken),
                         key=lambda t: -probs[t]["p_third_qual"])
    thirds = third_cands[:8]
    thirds_by_group = {probs[t]["group"]: t for t in thirds}
    third_assign = _allocate_thirds(_third_slots(bracket), thirds_by_group,
                                    random.Random(0))

    def resolve(spec, m):
        if "w" in spec:
            return winners.get(spec["w"])
        if "r" in spec:
            return runners.get(spec["r"])
        if "t" in spec:
            return third_assign.get(m)
        return None

    r32_card = [{"m": e["m"], "home": resolve(e["a"], e["m"]),
                 "away": resolve(e["b"], e["m"])} for e in bracket["r32"]]
    return {"winners": winners, "runners": runners,
            "thirds": thirds_by_group, "r32": r32_card}


def calibration_check(sim: Dict) -> List[Dict]:
    """Compare the sim's realised knockout rates to the historical targets
    (data/history.json). Returns one row per metric with an ok/off flag, so a
    drift in the ET/penalty/goals machinery is caught loudly."""
    cal = sim.get("calibration", {})
    tgt = cal.get("targets", {})
    checks = [
        ("Prolongations (part des KO)", cal.get("realized_et_share"),
         tgt.get("share_to_extra_time"), 0.08),
        ("Tirs au but (part des KO)", cal.get("realized_pen_share"),
         tgt.get("share_to_penalties"), 0.06),
        ("Buts/match KO", cal.get("realized_goals_pg"),
         tgt.get("goals_per_game_knockout"), 0.45),
    ]
    rows = []
    for label, got, target, tol in checks:
        ok = (got is not None and target is not None and abs(got - target) <= tol)
        rows.append({"metric": label, "realized": got, "target": target,
                     "tol": tol, "ok": ok})
    return rows
