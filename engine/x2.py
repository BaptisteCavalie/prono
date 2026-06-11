"""MPP x2 bonus policy: when to burn the one tournament-long doubler, and on what.

The x2 doubles EVERY point of a single prono (cote + rarity bonus), once per
tournament. Its marginal value on a match is therefore exactly that match's
expected MPP points (doubling adds +E[points]), so the *candidate* question is
trivial with our infra: take the slate's highest E[MPP]. The hard question is
*timing* — burning it on matchday 1 forfeits every better-informed spot later.

The timing tree below codifies the playbook logic (group stage = never on MD1,
only as a comeback weapon afterwards; R32 = only on a standout; R16 = the
optimal window: every team has played 4+ matches, cotes are higher than the
group stage and 8 matches give real choice; QF = last call; SF/final = forced,
or a leader's insurance). Position-awareness mirrors engine/mpp.py modes: a
leader saves the x2 as late insurance, a trailing player fires it earlier.
"""
from __future__ import annotations

from typing import Dict, List, Optional

STAGES = ("group_md1", "group", "r32", "r16", "qf", "sf", "final")

# Trailing by this much makes the x2 a comeback weapon already in the groups.
GROUP_EMERGENCY_BEHIND = 80.0
# In the R32, only a standout expected haul justifies not waiting for the R16.
R32_STANDOUT_EXP = 45.0

_STAGE_LABEL = {
    "group_md1": "groupes MD1", "group": "groupes", "r32": "16es (R32)",
    "r16": "8es (R16)", "qf": "quarts", "sf": "demi-finales", "final": "finale",
}


def advise(stage: str, points_behind: float = 0.0, leading: bool = False,
           best_exp: Optional[float] = None) -> Dict:
    """Timing advice for the x2 at a given stage of the tournament.

    Returns {"action": "use"|"save", "reason": str}. `points_behind` is your
    gap to the league leader (0 if leading/unknown); `leading` flags a lead
    worth protecting; `best_exp` is the slate's best E[MPP] (used in the R32).
    """
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}, got {stage!r}")

    if stage == "group_md1":
        return {"action": "save",
                "reason": "jamais en MD1 — aucune info sur les équipes, "
                          "et chaque tour suivant offre un meilleur spot"}
    if stage == "group":
        if points_behind >= GROUP_EMERGENCY_BEHIND:
            return {"action": "use",
                    "reason": f"retard de {points_behind:.0f} pts — arme de "
                              "remontada: la plus grosse E[MPP] du jour"}
        return {"action": "save", "reason": "garder pour les 8es (fenêtre optimale)"}
    if stage == "r32":
        if best_exp is not None and best_exp >= R32_STANDOUT_EXP:
            return {"action": "use",
                    "reason": f"E[MPP] {best_exp:.1f} >= {R32_STANDOUT_EXP:.0f} — "
                              "spot exceptionnel, ne pas attendre les 8es"}
        return {"action": "save", "reason": "pas de spot exceptionnel — les 8es "
                                            "restent la fenêtre optimale"}
    if stage == "r16":
        if leading:
            return {"action": "save",
                    "reason": "en tête — garder le x2 en assurance sur un pick "
                              "sûr en quarts/demies"}
        return {"action": "use",
                "reason": "fenêtre optimale: 4+ matchs vus par équipe, cotes "
                          "plus hautes, 8 matchs au choix"}
    if stage == "qf":
        if leading:
            return {"action": "save", "reason": "en tête — assurance demies/finale"}
        return {"action": "use", "reason": "dernier vrai créneau — ne pas garder "
                                           "le x2 au-delà des quarts"}
    # sf / final: last chance, use it whatever the position.
    return {"action": "use",
            "reason": f"{_STAGE_LABEL[stage]} — dernière occasion, le x2 ne se "
                      "reporte pas"}


def best_candidate(rows: List[Dict]) -> Optional[Dict]:
    """Highest expected-MPP match of a slate — the x2 target if firing today.

    Each row needs a `rec` (mpp.recommend output); returns the winning row with
    `x2_gain` (the extra points doubling is worth in expectation) attached.
    """
    scored = [r for r in rows if r.get("rec")]
    if not scored:
        return None
    best = max(scored, key=lambda r: r["rec"]["exp_points"])
    return {**best, "x2_gain": best["rec"]["exp_points"]}
