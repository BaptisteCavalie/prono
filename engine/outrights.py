"""Value bets on outright / stage markets (champion, finalist, group winner,
qualification…), priced off the tournament simulation.

A single-match value bet compares the model's 1X2 to the match odds. An outright
is the same idea one level up: compare the SIMULATION's probability that a team
reaches a stage (engine/tournament.py) to the bookmaker's outright price. This
is the only sound way to bet a deep run — chaining single-match favourites
overstates it badly (knockouts are ~2/3 favourite), and the bookmaker's outright
already integrates the whole bracket, so only a full forward sim can find the
mispriced ones.

Same safety doctrine as engine/betting.py and for the same backtested reason
(the model is overconfident): de-vig the market, SHRINK the sim probability
toward the market's fair probability, require a real edge AND positive EV, then
size with fractional Kelly under a hard per-bet cap. Long-odds outrights are
high-variance, so the caps are tighter than the single-match ones.

Bookmaker odds live in data/outrights.json, written by the ask-Claude layer like
scores/odds/bets — never fetched live, never invented. Absent file → no bets.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from engine import betting, data, model

# Tighter than single-match betting: outrights are long-odds, high-variance.
MARKET_WEIGHT = 0.50        # blend sim<-market (same overconfidence guard)
MIN_EDGE = 0.03             # require >=3pt edge on the SHRUNK probability
MAX_PLAUSIBLE_EDGE = 0.20   # raw edge above this = likely a stale/typo price, skip
KELLY_FRACTION = 0.20       # fifth-Kelly (long shots punish over-staking)
MAX_STAKE_FRAC = 0.015      # hard cap: 1.5% of the outright budget per bet

# Market key -> (label, the engine/tournament.py per-team probability field). A
# "winner_group_X" market maps to p_first restricted to group X (handled below).
MARKETS: Dict[str, tuple] = {
    "champion": ("Vainqueur", "p_champion"),
    "finalist": ("Finaliste", "p_final"),
    "reach_final": ("Finaliste", "p_final"),
    "reach_sf": ("Demi-finaliste", "p_sf"),
    "reach_qf": ("Quart de finaliste", "p_qf"),
    "reach_r16": ("8es de finale", "p_r16"),
    "qualify": ("Qualifié (R32)", "p_qualify"),
    "advance": ("Qualifié (R32)", "p_qualify"),
}


def _prob_field_for(market: str) -> Optional[str]:
    if market in MARKETS:
        return MARKETS[market][1]
    if market.startswith("winner_group_"):
        return "p_first"
    return None


def market_label(market: str) -> str:
    if market in MARKETS:
        return MARKETS[market][0]
    if market.startswith("winner_group_"):
        return f"1er groupe {market.rsplit('_', 1)[-1].upper()}"
    return market


def evaluate_market(prices: Dict[str, float], prob: Callable[[str], float],
                    market_weight: float = MARKET_WEIGHT) -> List[Dict]:
    """Value selections in ONE outright market.

    ``prices``: ``{team: decimal_odds}`` for every listed selection (the whole
    market, so it can be de-vigged). ``prob``: team -> simulation probability.
    Returns the value bets (edge + EV positive on the shrunk prob), best first.
    """
    teams = [t for t, o in prices.items() if isinstance(o, (int, float)) and o > 1]
    if not teams:
        return []
    decs = [float(prices[t]) for t in teams]
    fair = model.devig(decs)                       # strip the book's margin
    sim_p = [max(0.0, min(1.0, prob(t))) for t in teams]
    shrunk = betting.shrink_probs(sim_p, fair, market_weight)

    out = []
    for t, mp, sp, fp, dec in zip(teams, sim_p, shrunk, fair, decs):
        raw_edge = mp - fp
        if raw_edge > MAX_PLAUSIBLE_EDGE:          # too good to be true -> skip
            continue
        edge = sp - fp
        ev = sp * dec - 1.0
        if edge < MIN_EDGE or ev <= 0:
            continue
        stake = min(MAX_STAKE_FRAC, KELLY_FRACTION * betting.kelly_fraction(sp, dec))
        if stake <= 0:
            continue
        out.append({"team": t, "odds": dec, "sim": mp, "shrunk": sp, "fair": fp,
                    "edge": edge, "ev": ev, "stake_frac": stake})
    return sorted(out, key=lambda c: c["ev"], reverse=True)


def find_value(sim: Dict, board: Optional[Dict] = None) -> List[Dict]:
    """All outright value bets across every market in data/outrights.json.

    ``sim`` is an engine/tournament.py projection. ``board`` defaults to the
    loaded outrights file. Returns rows ``{market, label, ...bet}`` best EV first;
    empty when no odds are supplied (the common case until Baptiste dictates them).
    """
    board = board if board is not None else load_outrights()
    markets = (board or {}).get("markets", {})
    teams = sim.get("teams", {})
    rows: List[Dict] = []
    for market, prices in markets.items():
        field = _prob_field_for(market)
        if field is None or not isinstance(prices, dict):
            continue
        if market.startswith("winner_group_"):
            grp = market.rsplit("_", 1)[-1].upper()
            def prob(t, _f=field, _g=grp):
                row = teams.get(t)
                return row.get(_f, 0.0) if row and row.get("group") == _g else 0.0
        else:
            def prob(t, _f=field):
                row = teams.get(t)
                return row.get(_f, 0.0) if row else 0.0
        for bet in evaluate_market(prices, prob):
            rows.append({"market": market, "label": market_label(market), **bet})
    return sorted(rows, key=lambda r: r["ev"], reverse=True)


def load_outrights() -> Dict:
    """Bookmaker outright odds (data/outrights.json), ask-Claude-written.

    Shape: ``{"markets": {"champion": {"France": 4.5, ...}, "winner_group_A":
    {...}, "qualify": {...}}}``. Optional file, tolerant of broken JSON: a
    malformed tracking file must never crash the Paris page."""
    import json
    try:
        with open(data.DATA_DIR / "outrights.json", encoding="utf-8") as f:
            raw = json.load(f)
    except (FileNotFoundError, ValueError, OSError):
        return {"markets": {}}
    return raw if isinstance(raw, dict) else {"markets": {}}
