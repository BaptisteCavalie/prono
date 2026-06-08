#!/usr/bin/env python3
"""Local web UI for the WC2026 prediction engine (stdlib only)."""
from __future__ import annotations

import argparse
import html
import json
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from engine import autonomous, betting, data, data_quality, model, mpp, odds as oddsmod, odds_fetch, solidity, strategies, team_signals, updater

ROOT = Path(__file__).resolve().parent


def _split_match(s: str):
    for sep in (" vs ", " VS ", " v ", "/", " - "):
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return None


def _parse_date(s: str):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_completed(match: Dict) -> bool:
    return match.get("actual_home") is not None and match.get("actual_away") is not None


def _effective_date(match: Dict) -> Optional[str]:
    raw = match.get("date")
    if raw:
        return str(raw)[:10]

    group = str(match.get("group") or "A").upper()
    md = int(match.get("matchday") or 1)
    group_idx = max(0, ord(group[0]) - ord("A")) if group and "A" <= group[0] <= "Z" else 0

    # Fallback calendrier when fixture dates are not yet provided in data.
    md_start = {
        1: date(2026, 6, 11),
        2: date(2026, 6, 19),
        3: date(2026, 6, 27),
    }.get(md, date(2026, 6, 11))
    d = md_start + timedelta(days=group_idx // 2)
    return d.isoformat()


def _load_odds_board(path: Optional[str]) -> Dict[str, List[float]]:
    if not path:
        return {}

    resolved = (ROOT / path).resolve()
    if not resolved.is_file():
        raise ValueError(f"odds file not found: {path}")

    with open(resolved, encoding="utf-8") as f:
        raw = json.load(f)

    board = {}
    for key, triple in raw.items():
        if (not isinstance(triple, list) or len(triple) != 3
                or not all(isinstance(x, (int, float)) for x in triple)):
            raise ValueError(f"invalid odds for {key!r}; expected [home, draw, away]")

        if key.lower().startswith("g"):
            board[key.upper()] = [float(x) for x in triple]
            continue

        pair = _split_match(key)
        if pair:
            board[f"{pair[0].lower()}|{pair[1].lower()}"] = [float(x) for x in triple]
            continue

        raise ValueError(f"invalid odds key {key!r}; use fixture id or 'Home vs Away'")

    return board


def _default_odds_file() -> str:
    """Auto-fetched odds first, then an optional manual file. No demo data, so the
    Paris page only ever shows odds that are really there."""
    for cand in ("data/odds.json", "data/odds_md1.json"):
        if (ROOT / cand).is_file():
            return cand
    return ""


def _match_key(match: Dict) -> str:
    return f"{match['home'].lower()}|{match['away'].lower()}"


def _find_match_odds(match: Dict, board: Dict[str, List[float]]):
    return board.get(str(match.get("id", "")).upper()) or board.get(_match_key(match))


def _select_fixtures(fixtures: List[Dict], date_value: str, matchday: str) -> List[Dict]:
    def sort_key(m: Dict):
        return (_effective_date(m) or "9999-99-99", m.get("matchday") or 99, m.get("id") or "")

    if date_value:
        target = _parse_date(date_value)
        selected = [m for m in fixtures if _effective_date(m) and _parse_date(_effective_date(m)) == target]
        return sorted(selected, key=sort_key)

    if not matchday:
        return sorted(fixtures, key=sort_key)

    try:
        md = int(matchday)
    except ValueError:
        return sorted(fixtures, key=sort_key)

    selected = [m for m in fixtures if m.get("matchday") == md]
    return sorted(selected, key=sort_key)


def _confidence_nutriscore(prob: float, est: bool) -> str:
    score = prob
    if est:
        score -= 0.04
    if score >= 0.62:
        return "A"
    if score >= 0.56:
        return "B"
    if score >= 0.50:
        return "C"
    if score >= 0.44:
        return "D"
    return "E"


def _iso_to_flag(code: str) -> str:
    if not code or len(code) != 2:
        return "🏳"
    base = 127397
    return chr(base + ord(code[0].upper())) + chr(base + ord(code[1].upper()))


TEAM_TO_ISO = {
    "Algeria": "DZ",
    "Argentina": "AR",
    "Australia": "AU",
    "Austria": "AT",
    "Belgium": "BE",
    "Bosnia-Herzegovina": "BA",
    "Brazil": "BR",
    "Canada": "CA",
    "Cape Verde": "CV",
    "Colombia": "CO",
    "Croatia": "HR",
    "Curacao": "CW",
    "Curaçao": "CW",
    "Czechia": "CZ",
    "DR Congo": "CD",
    "Ecuador": "EC",
    "Egypt": "EG",
    "England": "GB",
    "France": "FR",
    "Germany": "DE",
    "Ghana": "GH",
    "Haiti": "HT",
    "Iran": "IR",
    "Iraq": "IQ",
    "Ivory Coast": "CI",
    "Japan": "JP",
    "Jordan": "JO",
    "Mexico": "MX",
    "Morocco": "MA",
    "Netherlands": "NL",
    "New Zealand": "NZ",
    "Norway": "NO",
    "Panama": "PA",
    "Paraguay": "PY",
    "Portugal": "PT",
    "Qatar": "QA",
    "Saudi Arabia": "SA",
    "Scotland": "GB",
    "Senegal": "SN",
    "South Africa": "ZA",
    "South Korea": "KR",
    "Spain": "ES",
    "Sweden": "SE",
    "Switzerland": "CH",
    "Tunisia": "TN",
    "Turkiye": "TR",
    "Türkiye": "TR",
    "United States": "US",
    "Uruguay": "UY",
    "Uzbekistan": "UZ",
}


def _team_flag(team: str) -> str:
    code = TEAM_TO_ISO.get(team)
    if not code:
        return "🏳"
    return _iso_to_flag(code)


def _fr_strategy_flag(text: str) -> str:
    mapping = [
        ("DRAW lean", "Tendance NUL"),
        ("group draws are historically underpriced", "les nuls de phase de groupes sont historiquement sous-cotes"),
        ("check the draw price", "verifie la cote du nul"),
        ("model draw", "modele nul"),
        ("UNDER 2.5 lean", "Tendance UNDER 2.5"),
        ("knockouts run low-scoring", "les matchs a elimination directe sont souvent fermes"),
        ("model U2.5", "modele U2.5"),
        ("HOST", "PAYS HOTE"),
        ("on home soil; hosts overperform their price", "a domicile: les pays hotes surperforment souvent leur cote"),
    ]
    out = text
    for src, dst in mapping:
        out = out.replace(src, dst)
    return out


def _best_selection(home: str, away: str, out: Dict):
    return max(
        (("home", f"Victoire {home}", out["p_home"]),
         ("draw", "Match nul", out["p_draw"]),
         ("away", f"Victoire {away}", out["p_away"])),
        key=lambda x: x[2],
    )


def _analyse_rows(fixtures: List[Dict], ratings: Dict, odds_board: Dict[str, List[float]],
                  team_status: Optional[Dict] = None):
    rows = []
    for m in fixtures:
        home = m["home"]
        away = m["away"]
        rh = ratings["teams"][home]
        ra = ratings["teams"][away]
        out = model.analyse(rh["rating"], ra["rating"], home_adv=m.get("home_adv", 0.0),
                            ad_home=model.ad_from_row(rh), ad_away=model.ad_from_row(ra))
        pick_sel, pick_label, pick_prob = _best_selection(home, away, out)

        (si, sj), sp = out["top_scores"][0]  # modal score (kept for the note below)
        est = rh.get("source") != "live" or ra.get("source") != "live"
        completed = _is_completed(m)
        actual_score = None
        if completed:
            actual_score = f"{m.get('actual_home')}-{m.get('actual_away')}"

        odds = _find_match_odds(m, odds_board)

        # MPP-optimal prono: the scoreline that maximises expected Mon Petit Prono
        # points (consistent with the favoured 1N2, then rarity-bonus aware), not
        # just the single most-likely scoreline.
        rec = mpp.recommend(out, odds)
        rsi, rsj = rec["score"]
        live_predicted_score = f"{rsi}-{rsj}"
        frozen_home = _as_int(m.get("predicted_home"))
        frozen_away = _as_int(m.get("predicted_away"))
        preserved_predicted_score = None
        if frozen_home is not None and frozen_away is not None:
            preserved_predicted_score = f"{frozen_home}-{frozen_away}"
        predicted_score = preserved_predicted_score or live_predicted_score
        bet_label = pick_label
        bet_conf = round(pick_prob * 100)
        value_rows = []
        value_summaries = []

        if odds:
            value_rows = oddsmod.value_1x2(out, odds[0], odds[1], odds[2])
            value_candidates = [r for r in value_rows if r["value"]]
            if value_candidates:
                best = max(value_candidates, key=lambda r: r["ev"])
                bet_label = {
                    "home": f"Victoire {home} @ {best['odds']:.2f}",
                    "draw": f"Match nul @ {best['odds']:.2f}",
                    "away": f"Victoire {away} @ {best['odds']:.2f}",
                }[best["sel"]]
                bet_conf = round(best["model"] * 100)

            for val in value_candidates:
                side = {
                    "home": f"Victoire {home}",
                    "draw": "Match nul",
                    "away": f"Victoire {away}",
                }[val["sel"]]
                value_summaries.append(
                    f"{side} @ {val['odds']:.2f} (EV {val['ev'] * 100:+.1f}%)"
                )

        pick_odds = None
        if odds:
            pick_odds = {
                "home": odds[0],
                "draw": odds[1],
                "away": odds[2],
            }[pick_sel]

        notes = [_fr_strategy_flag(x) for x in strategies.flags(m, home, away, rh, ra, out)]
        for team, row in ((home, rh), (away, ra)):
            delta = float(row.get("status_delta", 0.0) or 0.0)
            if abs(delta) >= 0.5:
                sign = "+" if delta > 0 else ""
                notes.append(f"Signal terrain {team}: {sign}{delta:.1f} Elo (forme/blessures/cartons/news)")
            for n in team_signals.status_notes(team, team_status or {}):
                notes.append(f"{team}: {n}")
        if est:
            notes.append("Au moins une cote Elo est estimee. La confiance peut changer apres mise a jour des ratings live.")
        if not odds:
            notes.append("Aucune cote bookmaker chargee. Ajoutez un fichier JSON de cotes pour activer la comparaison modele vs marche.")
        elif not value_summaries:
            notes.append("Pas d'opportunite de value detectee avec les cotes actuelles.")

        if rec["differs"]:
            notes.append(
                f"Prono optimise Mon Petit Prono: {live_predicted_score} maximise les points "
                f"attendus (bonus score exact +{rec['bonus']} {rec['tier']}). Le score le plus "
                f"probable du modele reste {si}-{sj}."
            )
        if rec["bonus"] >= 70:
            notes.append(
                "Pari sur un score rare: gros bonus MPP mais probabilite plus faible. "
                "Plus risque — bon candidat pour le bonus X2."
            )

        if completed:
            notes.append("Match termine: le score affiche correspond au resultat final reel.")
            if preserved_predicted_score:
                notes.append("Prono conserve avant match: comparaison reel vs prono disponible directement.")
            else:
                notes.append("Prono non fige: lance 'python3 tools/snapshot_predictions.py' pour conserver les pronos avant les matchs.")

        rows.append({
            "id": m.get("id", ""),
            "group": m.get("group", "?"),
            "matchday": m.get("matchday", "?"),
            "date": _effective_date(m),
            "home": home,
            "away": away,
            "home_flag": _team_flag(home),
            "away_flag": _team_flag(away),
            "score": actual_score or predicted_score,
            "actual_score": actual_score,
            "score_conf": round(rec["p_exact"] * 100),
            "predicted_score": predicted_score,
            "predicted_score_live": live_predicted_score,
            "mpp_bonus": rec["bonus"],
            "mpp_tier": rec["tier"],
            "mpp_exp_points": round(rec["exp_points"], 1),
            "mpp_modal_score": f"{si}-{sj}",
            "mpp_differs": rec["differs"],
            "prediction_saved": bool(preserved_predicted_score),
            "prediction_changed": (
                bool(preserved_predicted_score)
                and not completed
                and live_predicted_score != preserved_predicted_score
            ),
            "bet": bet_label,
            "bet_conf": bet_conf,
            "pick_label": pick_label,
            "pick_sel": pick_sel,
            "pick_prob": pick_prob,
            "pick_odds": pick_odds,
            "odds": odds,
            "value_summaries": value_summaries,
            "notes": notes,
            "p_home": round(out["p_home"] * 100),
            "p_draw": round(out["p_draw"] * 100),
            "p_away": round(out["p_away"] * 100),
            "probs": {"home": out["p_home"], "draw": out["p_draw"], "away": out["p_away"]},
            "nutri": _confidence_nutriscore(pick_prob, est),
            "completed": completed,
            "est": est,
        })
    return rows


def _group_rows_by_matchday(rows: List[Dict]):
    grouped: Dict[str, List[Dict]] = {}
    for r in rows:
        day = str(r.get("date") or "")[:10]
        grouped.setdefault(day, []).append(r)

    ordered = sorted(grouped.items(), key=lambda kv: kv[0])
    for _, items in ordered:
        items.sort(key=lambda x: (x.get("date") or "", x.get("id") or ""))
    return ordered


def _fr_date_label(iso_date: str) -> str:
    months = {
        1: "janvier",
        2: "fevrier",
        3: "mars",
        4: "avril",
        5: "mai",
        6: "juin",
        7: "juillet",
        8: "aout",
        9: "septembre",
        10: "octobre",
        11: "novembre",
        12: "decembre",
    }
    d = _parse_date(iso_date)
    return f"{d.day} {months[d.month]} {d.year}"


def _build_recommendations(rows: List[Dict], bankroll: float = 50.0,
                           market_weight: Optional[float] = None,
                           kelly: Optional[float] = None):
    """Safe betting plan from the analysed rows (see engine/betting.py).

    Only value bets survive (model edge over the de-vigged price, on probabilities
    shrunk toward the market to tame overconfidence). Stakes are quarter-Kelly,
    hard-capped, sized off a deliberately small bankroll for a low-stakes crash
    test. Combos are limited to 2 independent value legs with a tiny ring-fenced
    stake. Built on the WC2022 backtest (tools/backtest_wc2022*)."""
    mw = betting.MARKET_WEIGHT if market_weight is None else market_weight
    kf = betting.KELLY_FRACTION if kelly is None else kelly

    future_rows = [r for r in rows if not r.get("completed")]
    if not future_rows:
        return None

    evals = []
    for r in future_rows:
        odds = r.get("odds")
        bet = None
        if odds:
            out = {"p_home": r["probs"]["home"], "p_draw": r["probs"]["draw"],
                   "p_away": r["probs"]["away"]}
            bet = betting.evaluate_single(out, tuple(odds), mw, kf)
        evals.append({
            "key": r.get("id", ""),
            "match_id": r.get("id", ""),
            "label": f"{r['home']} vs {r['away']}",
            "home": r["home"],
            "away": r["away"],
            "has_odds": bool(odds),
            "bet": bet,
        })

    singles = betting.plan_singles(evals, bankroll)            # value bets only, capped
    combos = betting.build_combos(singles, bankroll)           # <=2 legs, tiny stake

    n_with_odds = sum(1 for e in evals if e["has_odds"])
    single_stake = sum(s["stake"] for s in singles)
    combo_stake = sum(c["stake"] for c in combos)
    ev_profit = (sum(s["stake"] * s["bet"]["ev"] for s in singles)
                 + sum(c["stake"] * c["ev"] for c in combos))

    return {
        "singles": singles,
        "combos": combos,
        "bankroll": bankroll,
        "market_weight": mw,
        "kelly": kf,
        "n_future": len(future_rows),
        "n_with_odds": n_with_odds,
        "single_stake": single_stake,
        "combo_stake": combo_stake,
        "total_stake": single_stake + combo_stake,
        "ev_profit": ev_profit,
        "has_full_odds": n_with_odds > 0,
    }


def _sel_fr(sel: str, home: str, away: str) -> str:
    return {"home": f"Victoire {home}", "draw": "Match nul",
            "away": f"Victoire {away}"}.get(sel, sel)


def _paris_odds_status() -> str:
    """One-line note on where the odds come from (auto-fetch status)."""
    if odds_fetch.has_key():
        state = odds_fetch.read_state()
        if state.get("fetched_at"):
            return (f"<div class='legend'>Cotes auto via The Odds API — "
                    f"{state.get('matches', 0)} match(s), maj {html.escape(str(state['fetched_at']))}.</div>")
        return ("<div class='legend'>Cotes auto via The Odds API (cle detectee). "
                "La liste se remplit au prochain rafraichissement / quand des cotes WC sont publiees.</div>")
    return ("<div class='legend'>Cotes auto <strong>non configurees</strong>: ajoutez une cle gratuite "
            "The Odds API (env <code>ODDS_API_KEY</code> ou fichier <code>data/odds_api_key.txt</code>) "
            "pour activer la recuperation automatique des cotes. Sans cotes, aucune value n'est calculable.</div>")


def _health_level_ui(level: str) -> Dict[str, str]:
    lvl = (level or "").lower()
    if lvl == "good":
        return {
            "label": "Vert",
            "class": "health-good",
            "state": "OK",
            "can_bet": "1",
            "message": "Donnees a jour: vous pouvez generer des recommandations.",
        }
    if lvl == "warning":
        return {
            "label": "Orange",
            "class": "health-warning",
            "state": "Surveillance",
            "can_bet": "1",
            "message": "Donnees a surveiller: verifiez blessures, suspensions et compositions avant de parier.",
        }
    return {
        "label": "Rouge",
        "class": "health-critical",
        "state": "Bloque",
        "can_bet": "0",
        "message": "Donnees insuffisantes: mettez a jour fixtures, ratings et statut equipes pour debloquer les recommandations.",
    }


def _build_data_info(fixtures: List[Dict], ratings: Dict, team_status: Dict,
                     health: Optional[Dict], odds_file: str) -> Dict:
    teams = (ratings or {}).get("teams", {})
    total_teams = len(teams)
    live_teams = sum(1 for row in teams.values() if str(row.get("source", "")).lower() == "live")
    estimate_teams = max(0, total_teams - live_teams)

    completed_matches = sum(1 for m in fixtures if _is_completed(m))
    predicted_at_values = [str(m.get("predicted_at")) for m in fixtures if m.get("predicted_at")]
    latest_prediction_snapshot = max(predicted_at_values) if predicted_at_values else None

    return {
        "data_sources": [
            f"ratings.json: {(ratings or {}).get('source', 'n/a')}",
            f"team_status.json: {(team_status or {}).get('source', 'n/a')}",
            "fixtures.json: calendrier + scores reels + snapshots de prediction",
            (f"odds file: {odds_file}" if odds_file else "odds file: non charge (comparaison marche inactive)"),
        ],
        "information_sources": [
            "Ratings Elo (force de base par equipe)",
            "Signaux equipe: forme, blessures, suspensions, news",
            "Scores reels enregistres (mise a jour auto des ratings)",
            "Cotes bookmaker 1N2 (si fichier de cotes fourni)",
        ],
        "last_updates": {
            "ratings_as_of": (ratings or {}).get("as_of"),
            "team_status_as_of": (team_status or {}).get("as_of"),
            "latest_prediction_snapshot": latest_prediction_snapshot,
        },
        "quality_rating": {
            "score": (health or {}).get("score"),
            "level": (health or {}).get("level"),
        },
        "other": {
            "fixtures_total": len(fixtures),
            "fixtures_completed": completed_matches,
            "live_ratings": live_teams,
            "estimated_ratings": estimate_teams,
            "ratings_total": total_teams,
            "status_coverage_pct": (health or {}).get("status_coverage_pct"),
            "home_adv_coverage_pct": (health or {}).get("home_adv_coverage_pct"),
        },
    }


def _render_page(matchday: str, date_value: str, odds_file: str, no_auto: bool,
                 rows: List[Dict], applied_results: int, action: str,
                 recommendations: Optional[Dict], error: str = "", tab: str = "futurs",
                 health: Optional[Dict] = None, solidity_report: Optional[Dict] = None,
                 data_info: Optional[Dict] = None, bankroll: float = 50.0) -> bytes:
    safe_tab = tab if tab in ("futurs", "passes", "paris") else "futurs"
    title_tag = "Paris" if safe_tab == "paris" else "Calendrier"

    past_rows = [r for r in rows if r.get("completed")]
    future_rows = [r for r in rows if not r.get("completed")]
    shown_rows = [] if safe_tab == "paris" else (past_rows if safe_tab == "passes" else future_rows)
    grouped = _group_rows_by_matchday(shown_rows)
    health_meta = _health_level_ui(str((health or {}).get("level", "")))
    bet_blocked = health_meta["can_bet"] != "1"

    parts = [
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>WC2026 Calendrier Pronos</title>",
        "<style>",
        ":root{--bg:#f6f4ec;--surface:#fffefa;--surface-2:#f2eee3;--text:#1f2430;--muted:#5d6679;--line:#d8deea;--line-2:#b8c2d9;--brand:#0f5c78;--brand-ink:#f4fbff;--accent:#f2a541;--ok:#257942;--alert:#8f2736}",
        "*{box-sizing:border-box}",
        "body{font-family:'Trebuchet MS','Gill Sans','Avenir Next',sans-serif;margin:0;background:radial-gradient(circle at 12% 0%,#fefcf5 0,#f6f4ec 52%,#ebeff8 100%);color:var(--text)}",
        ".wrap{max-width:1320px;margin:0 auto;padding:22px 18px 34px}",
        ".mast{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;flex-wrap:wrap;margin-bottom:14px}",
        "h1{margin:0;font-size:clamp(1.4rem,2.3vw,2rem);letter-spacing:.3px;line-height:1.08}",
        ".subtitle{margin:6px 0 0;color:var(--muted);font-size:.95rem;max-width:70ch}",
        ".panel{background:var(--surface);border:1px solid var(--line);border-radius:18px;padding:14px 14px 12px;margin-bottom:14px;box-shadow:0 14px 34px rgba(24,37,66,.08)}",
        ".actions{display:flex;justify-content:flex-start;align-items:center;gap:8px}",
        "button{width:auto;min-height:38px;padding:8px 14px;border-radius:10px;border:0;background:var(--brand);color:var(--brand-ink);font:700 .88rem/1 'Trebuchet MS','Gill Sans','Avenir Next',sans-serif;cursor:pointer}",
        "button.alt{background:linear-gradient(135deg,#efb147,#d88421);color:#1e1406}",
        "button:hover{filter:brightness(1.06)}",
        ".btn-alt{display:inline-block;text-decoration:none;min-height:38px;padding:10px 14px;border-radius:10px;background:linear-gradient(135deg,#efb147,#d88421);color:#1e1406;font:700 .88rem/1.2 'Trebuchet MS','Gill Sans','Avenir Next',sans-serif;cursor:pointer}",
        ".btn-alt:hover{filter:brightness(1.06)}",
        ".btn-disabled{opacity:.55;cursor:not-allowed;background:#cbd3e0;color:#5d6679}",
        ".bet-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px;margin-top:10px}",
        ".bet-card{border:1px solid var(--line);border-radius:12px;padding:11px 12px;background:linear-gradient(160deg,#fefcf6,#eef5ff)}",
        ".bet-card .bet-title{font-weight:800;font-size:.95rem;margin-bottom:4px}",
        ".bet-card .bet-sel{font-weight:700;color:#10384d}",
        ".bet-card .bet-meta{font-size:.82rem;color:var(--muted);margin-top:4px;line-height:1.35}",
        ".bet-stake{display:inline-block;margin-top:6px;padding:5px 10px;border-radius:999px;background:#168a3d;color:#fff;font-weight:800;font-size:.85rem}",
        "input:focus-visible,button:focus-visible{outline:3px solid color-mix(in srgb,var(--brand) 40%,white);outline-offset:2px}",
        ".stats{display:flex;gap:8px;flex-wrap:wrap}",
        ".stamp{background:var(--surface-2);border:1px solid var(--line);border-radius:999px;padding:6px 10px;font-size:.78rem;color:var(--muted)}",
        "table{width:100%;border-collapse:separate;border-spacing:0 8px}",
        "th,td{padding:8px 10px;vertical-align:middle}",
        "thead th{text-align:left;font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em;padding-bottom:2px}",
        "tbody tr{background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:0 4px 12px rgba(15,30,55,.03)}",
        "tbody tr td:first-child{border-radius:12px 0 0 12px}",
        "tbody tr td:last-child{border-radius:0 12px 12px 0}",
        "td strong{font-weight:700}",
        ".nutri{display:inline-block;min-width:26px;text-align:center;padding:4px 8px;border-radius:999px;font-weight:700;font-size:.74rem;color:#fff}",
        ".nutri-a{background:#168a3d}",
        ".nutri-b{background:#4ea93a}",
        ".nutri-c{background:#d4a813}",
        ".nutri-d{background:#d37a1c}",
        ".nutri-e{background:#b33a2f}",
        ".md-title{display:flex;justify-content:space-between;gap:8px;align-items:center;margin:2px 2px 6px}",
        ".line-main{display:grid;grid-template-columns:minmax(120px,1fr) auto auto minmax(120px,1fr);align-items:center;gap:10px}",
        ".team-side{display:flex;align-items:center;gap:6px;min-width:0}",
        ".team-side.right{justify-content:flex-end}",
        ".team-name{font-size:1rem;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
        ".vs-dot{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}",
        ".score-wrap{display:inline-flex;align-items:center;gap:8px;justify-self:center}",
        ".score-chip{display:inline-flex;align-items:center;justify-content:center;min-width:72px;padding:7px 10px;border-radius:999px;background:linear-gradient(135deg,#0f5c78,#0a4a66);color:#f4fbff;font-weight:800;font-size:1rem;line-height:1}",
        ".change-dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:#ff922b;margin-left:7px;vertical-align:middle;cursor:help;box-shadow:0 0 0 0 rgba(255,146,43,.6);animation:changePulse 1.8s infinite}",
        "@keyframes changePulse{0%{box-shadow:0 0 0 0 rgba(255,146,43,.55)}70%{box-shadow:0 0 0 7px rgba(255,146,43,0)}100%{box-shadow:0 0 0 0 rgba(255,146,43,0)}}",
        "@media (prefers-reduced-motion:reduce){.change-dot{animation:none}}",
        ".score-dual{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}",
        ".score-chip-real{background:linear-gradient(135deg,#1e6f3f,#155b31);font-size:.86rem;min-width:88px}",
        ".score-chip-prono{background:linear-gradient(135deg,#4f5e79,#38465f);font-size:.86rem;min-width:98px}",
        ".flag{font-size:1.05rem}",
        ".tiny{font-size:.76rem;color:var(--muted)}",
        ".result-main{font-weight:700}",
        ".result-sub{font-size:.82rem;color:var(--muted)}",
        ".done-cell{white-space:nowrap}",
        ".done-toggle{width:18px;height:18px;accent-color:#0f5c78;cursor:pointer}",
        "tr.done-row{outline:2px solid #9ad0af;background:linear-gradient(180deg,#f6fff8,#ffffff)}",
        "details{border:0;background:transparent}",
        "summary{cursor:pointer;font-size:.82rem;color:var(--brand);font-weight:700;display:inline-block;padding:7px 12px;border:1px solid var(--line);border-radius:999px;background:#f7fbff}",
        "summary::marker{color:var(--brand)}",
        ".note-list{margin:8px 0 0;padding-left:16px;color:var(--muted);font-size:.8rem;line-height:1.3;background:#fbfdff;border:1px solid var(--line);border-radius:10px;padding-top:8px;padding-bottom:8px;padding-right:8px}",
        ".odds{font-size:.79rem;color:var(--muted)}",
        ".reco-grid{display:grid;grid-template-columns:repeat(2,minmax(250px,1fr));gap:10px}",
        ".reco-card{border:1px solid var(--line);border-radius:12px;padding:10px;background:linear-gradient(160deg,#fefcf6,#eef5ff)}",
        ".reco-card h3{margin:0 0 8px;font-size:1rem}",
        ".reco-line{margin:4px 0;font-size:.9rem}",
        ".modal{position:fixed;inset:0;background:rgba(10,16,30,.42);display:none;align-items:center;justify-content:center;padding:16px;z-index:9999}",
        ".modal.open{display:flex}",
        ".modal-panel{width:min(1120px,96vw);max-height:90vh;overflow:auto;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:14px;box-shadow:0 24px 70px rgba(8,20,40,.35)}",
        ".modal-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}",
        ".modal-close{width:auto;min-height:34px;padding:7px 10px;border-radius:8px;background:#d8e2f0;color:#10263a}",
        ".modal-columns{display:grid;grid-template-columns:1fr 1fr;gap:12px}",
        ".bet-list{display:grid;gap:8px}",
        ".bet-item{border:1px solid var(--line);border-radius:10px;padding:8px;background:#fbfdff}",
        ".bet-title{font-weight:700;font-size:.92rem}",
        ".bet-meta{font-size:.82rem;color:var(--muted)}",
        ".muted{color:var(--muted);font-size:.9rem}",
        ".err{background:var(--alert);color:#fff;padding:11px 12px;border-radius:10px;margin-bottom:10px}",
        ".legend{margin-top:8px;color:var(--muted);font-size:.82rem}",
        ".health-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 10px;font-size:.78rem;font-weight:700;border:1px solid transparent}",
        ".health-dot{display:inline-block;width:8px;height:8px;border-radius:50%}",
        ".health-good{background:#edf8f1;color:#1f6e3a;border-color:#9ad0af}",
        ".health-good .health-dot{background:#1f9d50}",
        ".health-warning{background:#fff6e7;color:#7c4b10;border-color:#f1cd8b}",
        ".health-warning .health-dot{background:#cc8a20}",
        ".health-critical{background:#fdecec;color:#8f2736;border-color:#e4a7b1}",
        ".health-critical .health-dot{background:#b03346}",
        ".guard-msg{margin-top:10px;padding:9px 10px;border-radius:10px;border:1px dashed #c69d5a;background:#fff8e8;color:#704313;font-size:.84rem}",
        "button[disabled]{opacity:.62;cursor:not-allowed;filter:none}",
        ".info-grid{display:grid;grid-template-columns:repeat(2,minmax(240px,1fr));gap:10px;margin-top:8px}",
        ".info-card{border:1px solid var(--line);border-radius:10px;background:#fbfdff;padding:10px}",
        ".info-card h4{margin:0 0 6px;font-size:.88rem}",
        ".info-list{margin:0;padding-left:17px;color:var(--muted);font-size:.82rem;line-height:1.35}",
        ".info-line{font-size:.82rem;color:var(--muted);margin:2px 0}",
        "@media (max-width:860px){.reco-grid{grid-template-columns:1fr}.modal-columns{grid-template-columns:1fr}}",
        "@media (max-width:860px){.info-grid{grid-template-columns:1fr}}",
        "@media (max-width:760px){.wrap{padding:14px 10px 20px}.panel{padding:11px 10px}.actions{margin-top:2px}.actions button{width:100%}.line-main{grid-template-columns:1fr;gap:6px}.team-side.right{justify-content:flex-start}.score-wrap{justify-self:start}.score-chip{min-width:64px;font-size:.95rem;padding:6px 9px}table thead{display:none}table,tbody,tr,td{display:block;width:100%}table{border-spacing:0 10px}tr{border:1px solid var(--line);border-radius:12px;padding:8px 9px;margin-bottom:8px;background:var(--surface)}tbody tr td:first-child,tbody tr td:last-child{border-radius:0}td{border:0;padding:4px 0}td::before{content:attr(data-label);display:block;color:var(--muted);font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;margin-bottom:2px}}",
        "</style></head><body><main class='wrap'>",
        "<header class='mast'>",
        "<div>",
        f"<h1>WC2026 Calendrier Pronos - {html.escape(title_tag)}</h1>",
        "<p class='subtitle'>Vue calendrier rapide: ouvrez un match pour voir les explications utiles a la decision.</p>",
        "</div>",
        "<div class='stats'>",
        f"<div class='stamp'>Resultats integres automatiquement: {applied_results}</div>",
        f"<div class='stamp'>Matchs a venir: {len(future_rows)}</div>",
        f"<div class='stamp'>Matchs joues: {len(past_rows)}</div>",
        "<div class='stamp' id='done-count'>Pronostics coches: 0</div>",
        f"<div class='stamp'>Qualite des donnees: {(health or {}).get('score', 'n/a')}/100</div>",
        f"<div class='stamp'>Solidite modele: {((solidity_report or {}).get('score') if (solidity_report or {}).get('score') is not None else 'n/a')}/100</div>",
        f"<div class='health-pill {health_meta['class']}'><span class='health-dot'></span>Feu data: {health_meta['label']} ({health_meta['state']})</div>",
        "</div>",
        "</header>",
    ]

    if error:
        parts.append(f"<div class='err'>{html.escape(error)}</div>")

    parts.extend([
        "<div class='panel'>",
        (
            "<div class='actions'><a class='btn-alt' href='/?tab=paris'>Voir les recommandations de paris</a></div>"
            if not bet_blocked
            else "<div class='actions'><span class='btn-alt btn-disabled'>Recommandations indisponibles (qualite critique)</span></div>"
        ),
        "<div class='actions' style='justify-content:flex-start;gap:8px;margin-top:10px'>",
        f"<a href='/?tab=futurs' class='stamp' style='text-decoration:none;{('background:#d9f0ff;border-color:#8db8d1;color:#11384d' if safe_tab == 'futurs' else '')}'>Futurs</a>",
        f"<a href='/?tab=passes' class='stamp' style='text-decoration:none;{('background:#d9f0ff;border-color:#8db8d1;color:#11384d' if safe_tab == 'passes' else '')}'>Passes</a>",
        f"<a href='/?tab=paris' class='stamp' style='text-decoration:none;{('background:#d9f0ff;border-color:#8db8d1;color:#11384d' if safe_tab == 'paris' else '')}'>Paris</a>",
        "</div>",
        f"<div class='guard-msg'>{html.escape(health_meta['message'])}</div>",
        "<div class='legend'>Chaque match affiche une date. Si vous voyez une incoherence, mettez a jour data/fixtures.json.</div>",
        "</div>",
    ])

    if health:
        level_label = {
            "good": "Bon",
            "warning": "A surveiller",
            "critical": "Critique",
        }.get(health.get("level"), "Inconnu")
        parts.extend([
            "<div class='panel'>",
            f"<strong>Qualite des donnees: {health.get('score')}/100 ({level_label})</strong> ",
            f"<span class='health-pill {health_meta['class']}' style='margin-left:8px'><span class='health-dot'></span>{health_meta['label']}</span>",
            "<details style='margin-top:8px'><summary>Pourquoi ce score ?</summary><ul class='note-list'>",
            f"<li>Dates manquantes: {health.get('fixtures_missing_dates', 0)}</li>",
            f"<li>Matchs passes sans score final: {health.get('fixtures_past_without_score', 0)}</li>",
            f"<li>Age ratings (jours): {health.get('ratings_age_days')}</li>",
            f"<li>Age signaux equipes (jours): {health.get('status_age_days')}</li>",
        ])
        if not health.get("alerts"):
            parts.append("<li>Aucune alerte: les donnees sont coherentes pour l'analyse actuelle.</li>")
        for a in health.get("alerts", []):
            parts.append(f"<li>{html.escape(a)}</li>")
        parts.extend(["</ul></details>"])

        if data_info:
            quality_map = {
                "good": "Bon",
                "warning": "A surveiller",
                "critical": "Critique",
            }
            q_score = (data_info.get("quality_rating") or {}).get("score")
            q_level = quality_map.get((data_info.get("quality_rating") or {}).get("level"), "Inconnu")
            status_cov = (data_info.get("other") or {}).get("status_coverage_pct")
            home_adv_cov = (data_info.get("other") or {}).get("home_adv_coverage_pct")
            status_cov_txt = "n/a" if status_cov is None else f"{round(status_cov * 100)}%"
            home_adv_cov_txt = "n/a" if home_adv_cov is None else f"{round(home_adv_cov * 100)}%"

            parts.extend([
                "<details style='margin-top:8px'><summary>Info donnees (sources + fraicheur)</summary>",
                "<div class='info-grid'>",
                "<section class='info-card'>",
                "<h4>Liste des data sources</h4>",
                "<ul class='info-list'>",
            ])
            for row in data_info.get("data_sources", []):
                parts.append(f"<li>{html.escape(str(row))}</li>")
            parts.extend([
                "</ul>",
                "</section>",
                "<section class='info-card'>",
                "<h4>Liste des information sources</h4>",
                "<ul class='info-list'>",
            ])
            for row in data_info.get("information_sources", []):
                parts.append(f"<li>{html.escape(str(row))}</li>")
            parts.extend([
                "</ul>",
                "</section>",
                "<section class='info-card'>",
                "<h4>Date de derniere mise a jour</h4>",
                f"<div class='info-line'>ratings.as_of: {html.escape(str((data_info.get('last_updates') or {}).get('ratings_as_of')))}</div>",
                f"<div class='info-line'>team_status.as_of: {html.escape(str((data_info.get('last_updates') or {}).get('team_status_as_of')))}</div>",
                f"<div class='info-line'>dernier snapshot prediction: {html.escape(str((data_info.get('last_updates') or {}).get('latest_prediction_snapshot')))}</div>",
                "</section>",
                "<section class='info-card'>",
                "<h4>Qualite + infos pertinentes</h4>",
                f"<div class='info-line'>Qualite des donnees: {html.escape(str(q_score))}/100 ({html.escape(q_level)})</div>",
                f"<div class='info-line'>Ratings live: {html.escape(str((data_info.get('other') or {}).get('live_ratings', 0)))}/{html.escape(str((data_info.get('other') or {}).get('ratings_total', 0)))}</div>",
                f"<div class='info-line'>Ratings estimes: {html.escape(str((data_info.get('other') or {}).get('estimated_ratings', 0)))}</div>",
                f"<div class='info-line'>Coverage team status: {html.escape(status_cov_txt)}</div>",
                f"<div class='info-line'>Coverage home_adv: {html.escape(home_adv_cov_txt)}</div>",
                f"<div class='info-line'>Matchs completes: {html.escape(str((data_info.get('other') or {}).get('fixtures_completed', 0)))}/{html.escape(str((data_info.get('other') or {}).get('fixtures_total', 0)))}</div>",
                "</section>",
                "</div>",
                "</details>",
            ])

        parts.append("</div>")

    if solidity_report:
        level_label = {
            "solid": "Solide",
            "mixed": "Moyenne",
            "fragile": "Fragile",
            "insufficient": "Insuffisant",
        }.get(solidity_report.get("level"), "Inconnu")
        score_text = "n/a" if solidity_report.get("score") is None else str(solidity_report.get("score"))
        parts.extend([
            "<div class='panel'>",
            f"<strong>Solidite du systeme: {score_text}/100 ({level_label})</strong>",
            "<details style='margin-top:8px'><summary>Comment ce score est calcule ?</summary><ul class='note-list'>",
            f"<li>Matchs evalues: {solidity_report.get('matches', 0)}</li>",
            f"<li>Precision 1N2: {('n/a' if solidity_report.get('result_accuracy') is None else str(round(solidity_report.get('result_accuracy') * 100)) + '%')}</li>",
            f"<li>Score exact touche: {('n/a' if solidity_report.get('exact_score_hit') is None else str(round(solidity_report.get('exact_score_hit') * 100)) + '%')}</li>",
            f"<li>Brier 1N2 (plus bas = mieux): {('n/a' if solidity_report.get('brier_1x2') is None else format(solidity_report.get('brier_1x2'), '.3f'))}</li>",
            f"<li>Log-loss 1N2 (plus bas = mieux): {('n/a' if solidity_report.get('logloss_1x2') is None else format(solidity_report.get('logloss_1x2'), '.3f'))}</li>",
            f"<li>RPS 1N2 (standard du domaine, plus bas = mieux): {('n/a' if solidity_report.get('rps_1x2') is None else format(solidity_report.get('rps_1x2'), '.3f'))}</li>",
            f"<li>Confiance moyenne des picks: {('n/a' if solidity_report.get('avg_pick_conf') is None else str(round(solidity_report.get('avg_pick_conf') * 100)) + '%')}</li>",
        ])
        if solidity_report.get("calibration_gap") is not None:
            parts.append(
                f"<li>Ecart calibration (confiance - precision): {(solidity_report.get('calibration_gap') * 100):+.1f} point(s)</li>"
            )
        else:
            parts.append("<li>Ecart calibration (confiance - precision): n/a</li>")
        buckets = solidity_report.get("confidence_buckets") or []
        if buckets:
            parts.append("<li>Calibration par tranche de confiance:</li>")
            for b in buckets:
                parts.append(
                    f"<li>{b['range']} | n={b['count']} | hit {round(b['hit_rate'] * 100)}% | conf {round(b['avg_conf'] * 100)}% | gap {(b['gap'] * 100):+.1f}pt</li>"
                )
        else:
            parts.append("<li>Calibration par tranche de confiance: n/a (aucun match termine)</li>")
        for a in solidity_report.get("alerts", []):
            parts.append(f"<li>{html.escape(a)}</li>")
        parts.extend(["</ul></details>", "</div>"])

    if safe_tab == "paris":
        rec = recommendations
        bk = (rec.get("bankroll") if rec else bankroll) or bankroll
        parts.extend([
            "<section class='panel'>",
            "<h2 style='margin:0 0 4px'>Recommandations de paris — strategie prudente</h2>",
            "<p class='subtitle'>Selection calculee automatiquement: uniquement de la <strong>value</strong> "
            "(le modele bat la cote de-marginee), probabilites <strong>ramenees vers le marche</strong> pour "
            "corriger l'exces de confiance, mises en <strong>quart-Kelly plafonnees</strong>, combines limites "
            f"a <strong>2 selections</strong>. Bankroll de test: {bk:.0f} EUR (petites mises).</p>",
            _paris_odds_status(),
            "</section>",
        ])

        if bet_blocked:
            parts.append("<div class='panel'><div class='muted'>Recommandations indisponibles: qualite des donnees critique. Mettez a jour fixtures, ratings et team_status.</div></div>")
        elif not rec:
            parts.append("<div class='panel'><div class='muted'>Aucun match a venir pour ce filtre.</div></div>")
        else:
            parts.extend([
                "<div class='panel'>",
                "<div class='stats'>",
                f"<div class='stamp'>Bankroll: {bk:.2f} EUR</div>",
                f"<div class='stamp'>Matchs analyses: {rec['n_future']}</div>",
                f"<div class='stamp'>Avec cotes: {rec['n_with_odds']}</div>",
                f"<div class='stamp'>Paris simples value: {len(rec['singles'])}</div>",
                f"<div class='stamp'>Combines: {len(rec['combos'])}</div>",
                f"<div class='stamp'>Mise totale: {rec['total_stake']:.2f} EUR</div>",
                f"<div class='stamp'>Gain attendu (modele): {rec['ev_profit']:+.2f} EUR</div>",
                "</div>",
                "<div class='legend'>Le \"gain attendu\" est l'esperance du modele: fiable seulement dans la mesure ou le modele est bien calibre (il a tendance a etre trop confiant). Misez petit.</div>",
                "</div>",
            ])

            parts.extend([
                "<section class='panel'>",
                "<h3 style='margin:0'>Paris simples (value uniquement)</h3>",
                "<div class='bet-grid'>",
            ])
            if rec["singles"]:
                for s in rec["singles"]:
                    b = s["bet"]
                    sel = _sel_fr(b["sel"], s["home"], s["away"])
                    ret = s["stake"] * b["odds"]
                    parts.extend([
                        "<article class='bet-card'>",
                        f"<div class='bet-title'>{html.escape(s['label'])}</div>",
                        f"<div class='bet-sel'>{html.escape(sel)} @ {b['odds']:.2f}</div>",
                        f"<div class='bet-meta'>Modele {round(b['model']*100)}% &rarr; ajuste {round(b['shrunk']*100)}% "
                        f"(juste marche {round(b['fair']*100)}%)<br>Avantage +{round(b['edge']*100)} pt &middot; EV {b['ev']*100:+.1f}%</div>",
                        f"<div><span class='bet-stake'>Miser {s['stake']:.2f} EUR</span> "
                        f"<span class='bet-meta'>retour si gagne ~{ret:.2f} EUR</span></div>",
                        "</article>",
                    ])
            else:
                parts.append("<div class='muted'>Aucune value detectee — ne pas parier ce creneau (c'est frequent, et c'est sain).</div>")
            parts.extend(["</div>", "</section>"])

            parts.extend([
                "<section class='panel'>",
                "<h3 style='margin:0'>Combines (2 selections max &middot; mise minime)</h3>",
                "<div class='bet-grid'>",
            ])
            if rec["combos"]:
                for c in rec["combos"]:
                    ret = c["stake"] * c["combined_odds"]
                    parts.append("<article class='bet-card'>")
                    parts.append(f"<div class='bet-title'>Combine {len(c['legs'])} selections</div>")
                    for idx, leg in enumerate(c["legs"], start=1):
                        pair = _split_match(leg["label"]) or (leg["label"], "")
                        sel_txt = _sel_fr(leg["sel"], pair[0], pair[1])
                        parts.append(
                            f"<div class='bet-sel'>{idx}. {html.escape(sel_txt)} @ {leg['odds']:.2f}</div>"
                            f"<div class='bet-meta'>{html.escape(leg['label'])}</div>"
                        )
                    parts.append(
                        f"<div class='bet-meta'>Cote combinee {c['combined_odds']:.2f} &middot; "
                        f"EV {c['ev']*100:+.1f}% &middot; proba modele {round(c['combined_prob']*100)}%</div>"
                    )
                    parts.append(
                        f"<div><span class='bet-stake'>Miser {c['stake']:.2f} EUR</span> "
                        f"<span class='bet-meta'>retour si gagne ~{ret:.2f} EUR</span></div>"
                    )
                    parts.append("</article>")
            else:
                parts.append("<div class='muted'>Aucun combine ne passe le filtre prudent — sautez les combines (ils ont perdu ~69% au backtest WC2022).</div>")
            parts.extend(["</div>", "</section>"])

            if not rec["has_full_odds"]:
                parts.append("<div class='panel'><div class='muted'>Aucune cote chargee: renseignez un fichier de cotes pour activer la comparaison modele vs marche.</div></div>")

    if not shown_rows and safe_tab != "paris":
        if safe_tab == "passes":
            parts.extend(["<div class='panel'><div class='muted'>Aucun match joue avec score final disponible pour l'instant.</div></div>"])
        else:
            parts.extend(["<div class='panel'><div class='muted'>Aucun match a venir a afficher pour ce filtre.</div></div>"])

    for day, md_rows in grouped:
        day_label = _fr_date_label(day)
        parts.extend([
            "<section class='panel'>",
            "<div class='md-title'>",
            f"<strong>{html.escape(day_label)}</strong>",
            f"<span class='tiny'>{len(md_rows)} matchs</span>",
            "</div>",
            "<table><thead><tr>",
            "<th>Contexte</th><th>Pronostique</th><th>Match + Resultat + Nutri</th><th>Infos</th>",
            "</tr></thead><tbody>",
        ])

        for r in md_rows:
            est = " *" if r["est"] else ""
            parts.append("<tr>")
            parts.append(
                f"<td data-label='Contexte'><div class='tiny'>J{html.escape(str(r['matchday']))} · Groupe {html.escape(str(r['group']))}</div>"
                f"<div class='tiny'>{html.escape(str(r['id']))}</div></td>"
            )
            match_ref = f"{r['id']}|{r['home']}|{r['away']}|{r['date']}"
            parts.append(
                f"<td data-label='Pronostique' class='done-cell'><input class='done-toggle' type='checkbox' aria-label='Marquer {html.escape(r['home'])} vs {html.escape(r['away'])} comme deja pronostique' data-match='{html.escape(match_ref)}'></td>"
            )
            if r["completed"]:
                score_block = (
                    f"<span class='score-wrap score-dual'><span class='score-chip score-chip-real'>Reel {html.escape(r['actual_score'] or r['score'])}</span>"
                    f"<span class='score-chip score-chip-prono'>Prono {html.escape(r['predicted_score'])}</span>"
                    f"<span class='nutri nutri-{html.escape(r['nutri'].lower())}'>{html.escape(r['nutri'])}</span></span>"
                )
            else:
                change_dot = ""
                if r.get("prediction_changed"):
                    change_tip = (
                        f"Prono mis a jour apres une maj des donnees : "
                        f"{r['predicted_score']} -> {r['predicted_score_live']}"
                    )
                    change_dot = (
                        f"<span class='change-dot' role='img' tabindex='0' "
                        f"aria-label='{html.escape(change_tip)}' "
                        f"title='{html.escape(change_tip)}'></span>"
                    )
                score_block = (
                    f"<span class='score-wrap'><span class='score-chip'>{html.escape(r['score'])}{change_dot}</span>"
                    f"<span class='nutri nutri-{html.escape(r['nutri'].lower())}'>{html.escape(r['nutri'])}</span></span>"
                )
            parts.append(
                f"<td data-label='Match + Resultat + Nutri'><div class='line-main'>"
                f"<div class='team-side'><span class='flag'>{r['home_flag']}</span><span class='team-name'>{html.escape(r['home'])}</span></div>"
                f"<span class='vs-dot'>vs</span>"
                f"{score_block}"
                f"<div class='team-side right'><span class='team-name'>{html.escape(r['away'])}</span><span class='flag'>{r['away_flag']}</span></div>"
                f"</div></td>"
            )

            parts.append("<td data-label='Infos'><details><summary>Infos utiles pour decider</summary><ul class='note-list'>")
            parts.append(
                f"<li>Probabilites 1N2 du modele: 1={r['p_home']}% | N={r['p_draw']}% | 2={r['p_away']}%</li>"
            )
            parts.append(
                f"<li>Score exact le plus probable: {html.escape(r['predicted_score'])} ({r['score_conf']}%)</li>"
            )
            parts.append(
                f"<li>Choix 1N2 le plus probable: {html.escape(r['pick_label'])} ({round(r['pick_prob'] * 100)}%), Nutri {html.escape(r['nutri'])}</li>"
            )
            parts.append(
                f"<li>Recommandation de pari actuelle: {html.escape(r['bet'])} ({r['bet_conf']}%{est})</li>"
            )
            if r.get("prediction_changed"):
                parts.append(
                    f"<li><strong>● Prono mis a jour</strong> : le prono fige etait "
                    f"{html.escape(r['predicted_score'])}, le modele estime maintenant "
                    f"{html.escape(r['predicted_score_live'])} apres une maj des donnees "
                    f"(ratings / forme / blessures / avantage hote / attaque-defense).</li>"
                )
            if r["completed"]:
                parts.append(f"<li>Prono conserve: {html.escape(r['predicted_score'])}</li>")
                if not r.get("prediction_saved"):
                    parts.append(f"<li>Note: prono non fige (estimation actuelle: {html.escape(r['predicted_score_live'])}).</li>")
            if r["odds"]:
                parts.append(
                    f"<li>Cotes bookmaker chargees: 1 {r['odds'][0]:.2f} / N {r['odds'][1]:.2f} / 2 {r['odds'][2]:.2f}</li>"
                )
            for vs in r["value_summaries"]:
                parts.append(f"<li>{html.escape(vs)}</li>")
            for note in r["notes"]:
                parts.append(f"<li>{html.escape(note)}</li>")
            parts.append("</ul></details></td>")
            parts.append("</tr>")

        parts.extend(["</tbody></table>", "</section>"])

    parts.extend([
        "<script>",
        "(function(){",
        "const key='wc2026_done_predictions_v1';",
        "const countEl=document.getElementById('done-count');",
        "const parse=()=>{try{return new Set(JSON.parse(localStorage.getItem(key)||'[]'));}catch(_){return new Set();}};",
        "const save=(set)=>localStorage.setItem(key,JSON.stringify(Array.from(set)));",
        "const refreshCount=(set)=>{if(countEl){countEl.textContent='Pronostics coches: '+set.size;}};",
        "const done=parse();",
        "const checks=document.querySelectorAll('.done-toggle');",
        "checks.forEach((box)=>{",
        "const id=box.getAttribute('data-match')||'';",
        "if(done.has(id)){box.checked=true;}",
        "const row=box.closest('tr');",
        "if(row&&box.checked){row.classList.add('done-row');}",
        "box.addEventListener('change',()=>{",
        "if(box.checked){done.add(id);}else{done.delete(id);}",
        "if(row){row.classList.toggle('done-row',box.checked);}",
        "save(done);refreshCount(done);",
        "});",
        "});",
        "refreshCount(done);",
        "})();",
        "</script>",
        "</main></body></html>",
    ])
    return "".join(parts).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        params = parse_qs(parsed.query)
        matchday = (params.get("matchday", [""])[0] or "").strip()
        date_value = (params.get("date", [""])[0] or "").strip()
        odds_file = (params.get("odds_file", [""])[0] or "").strip()
        action = (params.get("action", ["refresh"])[-1] or "refresh").strip().lower()
        tab = (params.get("tab", ["futurs"])[0] or "futurs").strip().lower()
        if action == "reco":          # back-compat: old reco button -> Paris page
            tab = "paris"
        if tab == "paris" and not odds_file:   # auto-source odds, no manual import
            odds_file = _default_odds_file()
        no_auto = (params.get("no_auto", [""])[0] or "") in ("1", "on", "true")
        try:
            bankroll = float((params.get("bankroll", ["50"])[0] or "50").strip())
        except ValueError:
            bankroll = 50.0
        if bankroll <= 0:
            bankroll = 50.0

        rows = []
        applied_results = 0
        error = ""
        recommendations = None
        health = None
        solidity_report = None
        data_info = None

        try:
            autonomous.autonomous_refresh()
            fixtures = data.load_fixtures()
            base_ratings = data.load_ratings()
            ratings = data.load_ratings()
            team_status = data.load_team_status()
            solidity_report = solidity.assess_model_solidity(fixtures, base_ratings)
            if not no_auto:
                ratings, applied_results = updater.apply_completed_results(ratings, fixtures)
            ratings = team_signals.adjust_ratings_with_status(ratings, team_status)
            health = data_quality.assess_data_health(fixtures, ratings, team_status)
            data_info = _build_data_info(fixtures, ratings, team_status, health, odds_file)

            selected = _select_fixtures(fixtures, date_value, matchday)
            if not selected:
                if date_value:
                    error = f"Aucun match trouve pour le {date_value}. Verifiez le format YYYY-MM-DD ou choisissez une autre date."
                else:
                    error = f"Aucun match trouve pour la journee {matchday}. Essayez une autre journee ou retirez le filtre."
            odds_board = _load_odds_board(odds_file)
            rows = _analyse_rows(selected, ratings, odds_board, team_status=team_status)
            if tab == "paris":
                if (health or {}).get("level") == "critical":
                    error = "Recommandations indisponibles: la qualite des donnees est critique. Mettez a jour fixtures, ratings et team_status puis reessayez."
                else:
                    recommendations = _build_recommendations(rows, bankroll=bankroll)
        except Exception as exc:
            error = str(exc)

        body = _render_page(
            matchday,
            date_value,
            odds_file,
            no_auto,
            rows,
            applied_results,
            action,
            recommendations,
            error,
            tab,
            health,
            solidity_report,
            data_info,
            bankroll,
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def main():
    parser = argparse.ArgumentParser(description="WC2026 local UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"UI running on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
