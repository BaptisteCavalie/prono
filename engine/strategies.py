"""Documented World Cup betting-edge heuristics, surfaced as leans/flags.

These encode *historical tendencies* from past tournaments (see README) — they
are modest, possibly decaying, and partly priced-in. Treat them as priors that
tilt close calls, NOT guarantees. The quantified version of an edge always
comes from comparing the model to real market odds (see engine/odds.py).
"""
from typing import Dict, List

HOST_NATIONS = {"United States", "Canada", "Mexico"}
STRONG_RATING = 1900       # "top side" threshold (Elo scale) for knockout-unders lean
GROUP_DRAW_FLAG = 0.26     # model draw prob above which the group-draw edge is notable


def flags(match: Dict, home: str, away: str,
          r_home: Dict, r_away: Dict, out: Dict) -> List[str]:
    out_flags: List[str] = []
    stage = match.get("stage", "group")

    # 1) Group-stage draws are historically underpriced.
    if stage == "group" and out["p_draw"] >= GROUP_DRAW_FLAG:
        out_flags.append(
            f"DRAW lean — group draws are historically underpriced "
            f"(model draw {round(out['p_draw'] * 100)}%; check the draw price)")

    # 2) Knockout games tighten up; unders 2.5 lean, especially strong vs strong.
    if stage != "group" and r_home["rating"] >= STRONG_RATING and r_away["rating"] >= STRONG_RATING:
        out_flags.append(
            f"UNDER 2.5 lean — knockouts run low-scoring "
            f"(model U2.5 {round((1 - out['p_over25']) * 100)}%)")

    # 3) Host nations historically overperform their price.
    hosts = [t for t in (home, away) if t in HOST_NATIONS]
    if hosts:
        out_flags.append(
            f"HOST — {', '.join(hosts)} on home soil; hosts overperform their price")

    return out_flags
