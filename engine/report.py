"""Render model output as a human-readable prediction card + Claude brief."""
from typing import Dict

from engine import calibration, mpp


def _pct(x: float) -> str:
    return f"{round(x * 100):d}%"


def _scores(top) -> str:
    return "   ".join(f"{i}-{j} {_pct(p)}" for (i, j), p in top[:4])


def confidence(out: Dict, both_live: bool) -> str:
    # Confidence reads off the *calibrated* distribution, not the raw (overconfident)
    # one — a 95% raw favourite is really ~85% (see engine/calibration.py).
    maxp = max(calibration.calibrated_1x2(out))
    level = "high" if maxp >= 0.55 else "medium" if maxp >= 0.45 else "low"
    if level == "high" and not both_live:
        level = "medium"  # never claim high confidence on estimated ratings
    return level


def _header_tag(match: Dict) -> str:
    parts = []
    if match.get("group"):
        parts.append(f"Group {match['group']}")
    if match.get("matchday"):
        parts.append(f"MD{match['matchday']}")
    if match.get("stage") and match["stage"] != "group":
        parts.append(str(match["stage"]))
    parts.append(match.get("venue", "neutral"))
    return " · ".join(parts)


def card(match: Dict, home: str, away: str,
         r_home: Dict, r_away: Dict, out: Dict, mode: str = "ev") -> str:
    both_live = r_home.get("source") == "live" and r_away.get("source") == "live"
    conf = confidence(out, both_live)
    ko = mpp.is_knockout(match)
    rec = mpp.recommend(out, knockout=ko, mode=mode)
    ri, rj = rec["score"]
    ko_tag = "  (120', prolongations comprises)" if ko else ""
    return "\n".join([
        "─" * 64,
        f" {home}  vs  {away}    · {_header_tag(match)}",
        f"   ratings: {home} {r_home['rating']} ({r_home['source']})  ·  "
        f"{away} {r_away['rating']} ({r_away['source']})",
        f"   1X2:   {home} {_pct(out['p_home'])}    "
        f"Draw {_pct(out['p_draw'])}    {away} {_pct(out['p_away'])}",
        f"   xG:    {home} {out['lambda_home']:.2f}  ·  "
        f"{away} {out['lambda_away']:.2f}",
        f"   scores: {_scores(out['top_scores'])}",
        f"   MPP prono: {ri}-{rj}  (+{rec['bonus']} {rec['tier']}, "
        f"E[MPP] {rec['exp_points']:.1f}){ko_tag}",
        f"   O2.5 {_pct(out['p_over25'])}   ·   BTTS {_pct(out['p_btts'])}"
        f"   ·   confidence: {conf}",
    ])


def brief(match: Dict, home: str, away: str,
          r_home: Dict, r_away: Dict, out: Dict) -> str:
    src = f"{r_home['source']}/{r_away['source']}"
    top = ", ".join(f"{i}-{j}" for (i, j), _ in out["top_scores"][:3])
    grp = f" (Group {match.get('group')})" if match.get("group") else ""
    rec = mpp.recommend(out, knockout=mpp.is_knockout(match))
    ri, rj = rec["score"]
    return "\n".join([
        f"ASK CLAUDE — {home} vs {away}{grp}",
        f"  model: {home} {_pct(out['p_home'])} / Draw {_pct(out['p_draw'])} "
        f"/ {away} {_pct(out['p_away'])}; top {top}; "
        f"O2.5 {_pct(out['p_over25'])}; BTTS {_pct(out['p_btts'])}; "
        f"xG {out['lambda_home']:.2f}-{out['lambda_away']:.2f}",
        f"  MPP prono: {ri}-{rj} (+{rec['bonus']} {rec['tier']}, "
        f"E[MPP] {rec['exp_points']:.1f})",
        f"  ratings: {src}",
        "  need from live research: confirmed XIs, injuries/suspensions, "
        "qualification scenario & motivation, weather/venue, last-3 form",
    ])


def render_flags(flags) -> str:
    return "\n".join(["   strategy leans:"] + [f"     - {f}" for f in flags])


def render_value(home: str, away: str, rows) -> str:
    label = {"home": home, "draw": "Draw", "away": away}
    lines = ["   value vs market (de-vigged):"]
    for r in rows:
        tag = "  <-- VALUE" if r["value"] else ""
        lines.append(
            f"     {label[r['sel']]:<16} model {_pct(r['model'])}  "
            f"fair {_pct(r['fair'])}  @{r['odds']:.2f}  "
            f"EV {r['ev'] * 100:+.1f}%{tag}")
    return "\n".join(lines)


def simple(match: Dict, home: str, away: str,
           r_home: Dict, r_away: Dict, out: Dict, value_rows=None,
           mode: str = "ev") -> str:
    # model-only prono (see engine/prediction.py); odds drive the value table below, not the scoreline
    rec = mpp.recommend(out, knockout=mpp.is_knockout(match), mode=mode)
    i, j = rec["score"]
    sp = rec["p_exact"]
    mi, mj = rec["modal_score"]
    est = "*" if (r_home.get("source") != "live"
                  or r_away.get("source") != "live") else ""
    tag = ""
    if match.get("group"):
        md = f"·MD{match['matchday']}" if match.get("matchday") else ""
        tag = f"   [{match['group']}{md}]"

    if value_rows is not None:
        best = max(value_rows, key=lambda r: r["ev"])
        if best["value"]:
            label = {"home": f"{home} win", "draw": "Draw",
                     "away": f"{away} win"}[best["sel"]]
            bet = (f"{label} @{best['odds']:.2f}   {round(best['model'] * 100)}%"
                   f"  (EV {best['ev'] * 100:+.0f}%)")
        else:
            bet = "none — no value vs the price"
    else:
        picks = [(f"{home} win", out["p_home"]), ("Draw", out["p_draw"]),
                 (f"{away} win", out["p_away"])]
        name, p = max(picks, key=lambda x: x[1])
        bet = f"{name}   {round(p * 100)}%{est}"

    ref = f"  (model top {mi}-{mj})" if rec["differs"] else ""
    return (f"{home} vs {away}{tag}\n"
            f"  prono   {i}-{j}   {round(sp * 100)}%{est}   "
            f"+{rec['bonus']} {rec['tier']}   E[MPP] {rec['exp_points']:.1f}{ref}\n"
            f"  bet     {bet}")
