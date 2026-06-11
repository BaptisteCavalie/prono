#!/usr/bin/env python3
"""Local web UI for the WC2026 prediction engine (stdlib only)."""
from __future__ import annotations

import argparse
import html
import json
import math
import traceback
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from engine import autonomous, betting, data, data_quality, expert_signals, live_ratings, mpp, odds as oddsmod, odds_fetch, prediction, solidity, strategies, team_signals, updater

ROOT = Path(__file__).resolve().parent


class UiError(ValueError):
    """Erreur métier dont le message est rédigé pour l'utilisateur final."""


def _split_match(s: str) -> Optional[Tuple[str, str]]:
    for sep in (" vs ", " VS ", " v ", "/", " - "):
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return None


def _parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _as_int(value) -> Optional[int]:
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

    # Confine manual odds files to data/ — the parameter is reachable from the URL.
    resolved = (ROOT / path).resolve()
    data_dir = (ROOT / "data").resolve()
    if not (resolved.is_relative_to(data_dir) and resolved.is_file()):
        raise UiError("Fichier de cotes introuvable : indiquez un fichier JSON du dossier data/ (ex. data/odds.json).")

    try:
        with open(resolved, encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError:
        raise UiError(f"Fichier de cotes illisible ({path}) : le contenu n'est pas du JSON valide.")

    board = {}
    for key, triple in raw.items():
        if (not isinstance(triple, list) or len(triple) != 3
                or not all(isinstance(x, (int, float)) for x in triple)):
            raise UiError(f"Cotes invalides pour {key!r} : attendu [domicile, nul, extérieur].")

        if key.lower().startswith("g"):
            board[key.upper()] = [float(x) for x in triple]
            continue

        pair = _split_match(key)
        if pair:
            board[f"{pair[0].lower()}|{pair[1].lower()}"] = [float(x) for x in triple]
            continue

        raise UiError(f"Clé de cotes invalide {key!r} : utilisez l'identifiant du match (ex. G1) ou « Domicile vs Extérieur ».")

    return board


def _apply_paris_kickoffs(fixtures: List[Dict]) -> None:
    """Rewrite each fixture's date to its Europe/Paris (France) calendar date using
    the kickoff time captured from the odds feed — the jetlag fix, so a US-evening
    game shows on the next day like it does in France. Adds kickoff_paris (HH:MM).
    Matches with no known kickoff keep their stored date."""
    kicks = odds_fetch.load_kickoffs()
    if not kicks:
        return
    for m in fixtures:
        ct = kicks.get(str(m.get("id", "")).upper())
        if not ct:
            continue
        d, t = odds_fetch.paris_parts(ct)
        if d:
            m["date"] = d
            m["kickoff_paris"] = t


def _match_key(match: Dict) -> str:
    return f"{match['home'].lower()}|{match['away'].lower()}"


def _find_match_odds(match: Dict, board: Dict[str, List[float]]) -> Optional[List[float]]:
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


def _subdivision_flag(region: str) -> str:
    """Emoji tag-sequence flag for a GB home nation (e.g. 'gbeng' -> England),
    so England/Scotland show their own flag instead of the Union Jack. Falls
    back to a plain black flag on renderers too old to support the sequence."""
    tags = "".join(chr(0xE0000 + ord(c)) for c in region)
    return "\U0001F3F4" + tags + "\U000E007F"


# Home nations have no ISO 3166-1 code of their own; use the RGI subdivision
# tag flags. Checked before TEAM_TO_ISO so they never fall through to "GB".
_SUBDIVISION_FLAGS = {
    "England": _subdivision_flag("gbeng"),
    "Scotland": _subdivision_flag("gbsct"),
    "Wales": _subdivision_flag("gbwls"),
}


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


# Noms affichés (l'UI est en français) ; les clés de données restent en anglais.
TEAM_FR = {
    "Algeria": "Algérie",
    "Argentina": "Argentine",
    "Australia": "Australie",
    "Austria": "Autriche",
    "Belgium": "Belgique",
    "Bosnia-Herzegovina": "Bosnie-Herzégovine",
    "Brazil": "Brésil",
    "Cape Verde": "Cap-Vert",
    "Colombia": "Colombie",
    "Croatia": "Croatie",
    "Curacao": "Curaçao",
    "Czechia": "Tchéquie",
    "DR Congo": "RD Congo",
    "Ecuador": "Équateur",
    "Egypt": "Égypte",
    "England": "Angleterre",
    "Germany": "Allemagne",
    "Haiti": "Haïti",
    "Iraq": "Irak",
    "Ivory Coast": "Côte d'Ivoire",
    "Japan": "Japon",
    "Jordan": "Jordanie",
    "Mexico": "Mexique",
    "Morocco": "Maroc",
    "Netherlands": "Pays-Bas",
    "New Zealand": "Nouvelle-Zélande",
    "Norway": "Norvège",
    "Saudi Arabia": "Arabie saoudite",
    "Scotland": "Écosse",
    "Senegal": "Sénégal",
    "South Africa": "Afrique du Sud",
    "South Korea": "Corée du Sud",
    "Spain": "Espagne",
    "Sweden": "Suède",
    "Switzerland": "Suisse",
    "Tunisia": "Tunisie",
    "Turkiye": "Turquie",
    "Türkiye": "Turquie",
    "United States": "États-Unis",
    "Uzbekistan": "Ouzbékistan",
    "Wales": "Pays de Galles",
}


def _team_label(team: str) -> str:
    return TEAM_FR.get(team, team)


def _team_flag(team: str) -> str:
    if team in _SUBDIVISION_FLAGS:
        return _SUBDIVISION_FLAGS[team]
    code = TEAM_TO_ISO.get(team)
    if not code:
        return "🏳"
    return _iso_to_flag(code)


def _fr_strategy_flag(text: str) -> str:
    mapping = [
        ("DRAW lean", "Tendance NUL"),
        ("group draws are historically underpriced", "les nuls de phase de groupes sont historiquement sous-cotés"),
        ("check the draw price", "vérifie la cote du nul"),
        ("model draw", "modèle nul"),
        ("UNDER 2.5 lean", "Tendance UNDER 2.5"),
        ("knockouts run low-scoring", "les matchs à élimination directe sont souvent fermés"),
        ("model U2.5", "modèle U2.5"),
        ("HOST", "PAYS HÔTE"),
        ("on home soil; hosts overperform their price", "à domicile : les pays hôtes surperforment souvent leur cote"),
    ]
    out = text
    for src, dst in mapping:
        out = out.replace(src, dst)
    return out


def _best_selection(home_label: str, away_label: str, out: Dict) -> Tuple[str, str, float]:
    return max(
        (("home", f"Victoire {home_label}", out["p_home"]),
         ("draw", "Match nul", out["p_draw"]),
         ("away", f"Victoire {away_label}", out["p_away"])),
        key=lambda x: x[2],
    )


def _analyse_rows(fixtures: List[Dict], ratings: Dict, odds_board: Dict[str, List[float]],
                  team_status: Optional[Dict] = None):
    rows = []
    expert_sources = expert_signals.load_sources()
    for m in fixtures:
        home = m["home"]
        away = m["away"]
        home_label = _team_label(home)
        away_label = _team_label(away)
        rh = ratings["teams"][home]
        ra = ratings["teams"][away]
        out = prediction.analyse_match(m, ratings)
        pick_sel, pick_label, pick_prob = _best_selection(home_label, away_label, out)

        (si, sj), sp = out["top_scores"][0]  # modal score (kept for the note below)
        est = rh.get("source") != "live" or ra.get("source") != "live"
        completed = _is_completed(m)
        actual_score = None
        if completed:
            actual_score = f"{m.get('actual_home')}-{m.get('actual_away')}"

        odds = _find_match_odds(m, odds_board)

        # MPP-optimal prono: the scoreline that maximises expected Mon Petit Prono
        # points (consistent with the favoured 1N2, then rarity-bonus aware), not
        # just the single most-likely scoreline. Model-only on purpose (see
        # engine/prediction.py): the calendar prono must match the frozen one,
        # and odds-driven betting lives on the Paris tab, not here.
        rec = mpp.recommend(out, knockout=mpp.is_knockout(m))
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
                    "home": f"Victoire {home_label} @ {best['odds']:.2f}",
                    "draw": f"Match nul @ {best['odds']:.2f}",
                    "away": f"Victoire {away_label} @ {best['odds']:.2f}",
                }[best["sel"]]
                bet_conf = round(best["model"] * 100)

            for val in value_candidates:
                side = {
                    "home": f"Victoire {home_label}",
                    "draw": "Match nul",
                    "away": f"Victoire {away_label}",
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
        for team, team_lbl, row in ((home, home_label, rh), (away, away_label, ra)):
            delta = float(row.get("status_delta", 0.0) or 0.0)
            if abs(delta) >= 0.5:
                sign = "+" if delta > 0 else ""
                notes.append(f"Signal terrain {team_lbl} : {sign}{delta:.1f} Elo (forme/blessures/cartons/news)")
            for n in team_signals.status_notes(team, team_status or {}):
                notes.append(f"{team_lbl} : {n}")
            edelta = float(row.get("expert_delta", 0.0) or 0.0)
            if abs(edelta) >= 0.5:
                sign = "+" if edelta > 0 else ""
                notes.append(f"Signal expert {team_lbl} : {sign}{edelta:.1f} Elo")
            for n in expert_signals.expert_notes(team, expert_sources):
                notes.append(n)
        if est:
            notes.append("Au moins une cote Elo est estimée. La confiance peut changer après mise à jour des ratings live.")
        if not odds:
            notes.append("Aucune cote bookmaker chargée pour ce match : la comparaison modèle vs marché est inactive.")
        elif not value_summaries:
            notes.append("Pas d'opportunité de value détectée avec les cotes actuelles.")

        if rec["differs"]:
            notes.append(
                f"Prono optimisé Mon Petit Prono : {live_predicted_score} maximise les points "
                f"attendus (bonus score exact +{rec['bonus']} {rec['tier']})."
            )
        if rec["bonus"] >= 70:
            notes.append(
                "Pari sur un score rare : gros bonus MPP mais probabilité plus faible. "
                "Plus risqué — bon candidat pour le bonus X2."
            )

        if completed:
            notes.append("Match terminé : le score affiché correspond au résultat final réel.")
            if preserved_predicted_score:
                notes.append("Prono conservé avant match : comparaison réel vs prono disponible directement.")
            else:
                notes.append("Prono non figé : lance 'python3 tools/snapshot_predictions.py' pour conserver les pronos avant les matchs.")

        rows.append({
            "id": m.get("id", ""),
            "group": m.get("group", "?"),
            "matchday": m.get("matchday", "?"),
            "date": _effective_date(m),
            "kickoff_paris": m.get("kickoff_paris"),
            "home": home,
            "away": away,
            "home_label": home_label,
            "away_label": away_label,
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
        2: "février",
        3: "mars",
        4: "avril",
        5: "mai",
        6: "juin",
        7: "juillet",
        8: "août",
        9: "septembre",
        10: "octobre",
        11: "novembre",
        12: "décembre",
    }
    d = _parse_date(iso_date)
    return f"{d.day} {months[d.month]} {d.year}"


def _eur(value: float, decimals: Optional[int] = None) -> str:
    """Format monétaire FR : « 50 € », « 2,50 € »."""
    if decimals is None:
        decimals = 0 if float(value).is_integer() else 2
    return f"{value:.{decimals}f}".replace(".", ",") + " €"


def _eur_signed(value: float) -> str:
    return f"{value:+.2f}".replace(".", ",") + " €"


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
        when = ""
        if r.get("date"):
            try:
                when = _fr_date_label(r["date"])
            except ValueError:
                when = str(r["date"])
            if r.get("kickoff_paris"):
                when += f" · {r['kickoff_paris']} (heure FR)"
        evals.append({
            "key": r.get("id", ""),
            "match_id": r.get("id", ""),
            "label": f"{r['home_label']} vs {r['away_label']}",
            "home": r["home_label"],
            "away": r["away_label"],
            "when": when,
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


def _odds_source_note() -> str:
    """Ligne de statut de la source de cotes, quand une source est connectée."""
    if not odds_fetch.has_key():
        return ""
    state = odds_fetch.read_state()
    rem = state.get("remaining_credits")
    credits = f" · crédits restants : {rem}" if isinstance(rem, int) else ""
    if state.get("fetched_at"):
        n_matches = int(state.get("matches", 0) or 0)
        return (f"<div class='legend'>Cotes via The Odds API — {n_matches} match(s), "
                f"mises à jour {html.escape(str(state['fetched_at']))}{html.escape(credits)}.</div>")
    return ("<div class='legend'>Source de cotes connectée (The Odds API). La liste se remplit "
            f"dès que des cotes Coupe du Monde sont publiées{html.escape(credits)}.</div>")


def _health_level_ui(level: str) -> Dict[str, str]:
    lvl = (level or "").lower()
    if lvl == "good":
        return {
            "label": "Vert",
            "class": "health-good",
            "state": "OK",
            "can_bet": "1",
            "message": "Données à jour : vous pouvez générer des recommandations.",
        }
    if lvl == "warning":
        return {
            "label": "Orange",
            "class": "health-warning",
            "state": "Surveillance",
            "can_bet": "1",
            "message": "Données à surveiller : vérifiez blessures, suspensions et compositions avant de parier.",
        }
    return {
        "label": "Rouge",
        "class": "health-critical",
        "state": "Bloqué",
        "can_bet": "0",
        "message": "Données insuffisantes : mettez à jour fixtures, ratings et statut équipes pour débloquer les recommandations.",
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
            "fixtures.json: calendrier + scores réels + snapshots de prédiction",
            (f"odds file: {odds_file}" if odds_file else "odds file: non chargé (comparaison marché inactive)"),
        ],
        "information_sources": [
            "Ratings Elo (force de base par équipe)",
            "Signaux équipe : forme, blessures, suspensions, news",
            "Scores réels enregistrés (mise à jour auto des ratings)",
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


_TAB_LABELS = {"futurs": "Futurs", "passes": "Passés", "paris": "Paris"}

_CSS = "".join([
    ":root{--bg:#f6f4ec;--surface:#fffefa;--surface-2:#f2eee3;--surface-3:#fbfdff;"
    "--text:#1f2430;--muted:#5d6679;--line:#d8deea;--line-2:#b8c2d9;--track:#e7ebf3;"
    "--brand:#0f5c78;--brand-dark:#0a4a66;--brand-ink:#f4fbff;--brand-soft:#eaf2f8;"
    "--ok:#257942;--ok-bg:#edf8f1;--ok-line:#9ad0af;"
    "--warn:#e8590c;--warn-text:#7c4b10;--warn-bg:#fff6e7;--warn-line:#f1cd8b;"
    "--alert:#8f2736;--alert-bg:#fdecec;--alert-line:#e4a7b1;"
    "--neutral:#64748b;--slate:#44536e;--away:#b45309;"
    "--nutri-a:#36b14f;--nutri-b:#8cc152;--nutri-c:#f0c000;--nutri-d:#ea8c2e;--nutri-e:#c0392b;--nutri-ink:#1c1407;"
    "--font-mono:ui-monospace,'SF Mono','Cascadia Mono',Menlo,Consolas,monospace;"
    "--shadow-floating:0 4px 16px rgb(0 0 0 / 0.10)}",
    "*{box-sizing:border-box}",
    "body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,'Apple Color Emoji','Segoe UI Emoji',sans-serif;margin:0;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;font-variant-numeric:tabular-nums}",
    ".wrap{max-width:1240px;margin:0 auto;padding:20px 18px 34px}",
    ".mast{display:flex;justify-content:space-between;align-items:flex-end;gap:14px;flex-wrap:wrap;margin-bottom:12px}",
    "h1{margin:0;font-size:clamp(1.3rem,2vw,1.7rem);letter-spacing:.2px;line-height:1.1}",
    ".subtitle{margin:5px 0 0;color:var(--muted);font-size:.9rem;max-width:70ch}",
    ".panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 14px 12px;margin-bottom:14px}",
    ".bet-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin-top:10px}",
    ".bet-card{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--surface-3)}",
    ".bet-sel-line{font-size:1.02rem;font-weight:700;line-height:1.3}",
    ".bet-odds{font-family:var(--font-mono);color:var(--brand-dark);white-space:nowrap}",
    ".bet-context{font-size:.8rem;color:var(--muted);margin-top:3px;line-height:1.35}",
    ".bet-card .bet-meta{font-size:.8rem;color:var(--muted);margin-top:4px;line-height:1.35}",
    ".bet-stake-line{display:flex;align-items:center;gap:9px;margin-top:9px;flex-wrap:wrap}",
    ".bet-stake{display:inline-block;padding:6px 11px;border-radius:999px;background:var(--ok);color:#fff;font-weight:700;font-size:.92rem;font-family:var(--font-mono)}",
    ".bet-return{font-size:.8rem;color:var(--muted)}",
    ".bet-why{margin-top:7px}",
    ".bet-why summary{font-size:.78rem;padding:3px 2px}",
    "a:focus-visible,summary:focus-visible,input:focus-visible,button:focus-visible{outline:3px solid color-mix(in srgb,var(--brand) 45%,white);outline-offset:2px;border-radius:6px}",
    ".stats{display:flex;gap:8px;flex-wrap:wrap}",
    ".stamp{background:var(--surface-2);border:1px solid var(--line);border-radius:999px;padding:6px 10px;font-size:.78rem;color:var(--muted)}",
    ".stamp-warn{background:var(--warn-bg);border-color:var(--warn-line);color:var(--warn-text);font-weight:700}",
    "table{width:100%;border-collapse:collapse;table-layout:fixed}",
    "th,td{padding:9px 8px;vertical-align:middle}",
    "thead th{text-align:left;font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em;padding-bottom:4px}",
    "tbody tr{border-top:1px solid var(--line)}",
    "tbody tr:hover{background:color-mix(in srgb,var(--brand) 3%,var(--surface))}",
    "td strong{font-weight:700}",
    ".nutri{display:inline-block;min-width:30px;text-align:center;padding:6px 0;border-radius:8px;font-weight:700;font-size:.88rem;color:var(--nutri-ink)}",
    ".nutri-a{background:var(--nutri-a)}",
    ".nutri-b{background:var(--nutri-b)}",
    ".nutri-c{background:var(--nutri-c)}",
    ".nutri-d{background:var(--nutri-d)}",
    ".nutri-e{background:var(--nutri-e);color:#fff}",
    ".md-title{display:flex;justify-content:space-between;gap:8px;align-items:baseline;position:sticky;top:44px;z-index:5;background:var(--surface);margin:-14px -14px 4px;padding:12px 14px 8px;border-bottom:1px solid var(--line);border-radius:14px 14px 0 0}",
    ".md-title h2{margin:0;font-size:1rem;font-weight:700}",
    ".day-saisis{font-family:var(--font-mono)}",
    ".cell-meta .kick{display:block;font-family:var(--font-mono);font-weight:700;font-size:.95rem;line-height:1.2}",
    ".cell-meta .kick-tbd{color:var(--muted);font-weight:400}",
    ".meta-sub{display:block;font-size:.72rem;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
    ".cell-teams{font-size:.98rem;line-height:1.35}",
    ".team-name{display:inline}",
    ".team-sep{color:var(--muted);margin:0 7px}",
    ".score-chip{display:inline-flex;align-items:center;justify-content:center;min-width:72px;padding:7px 10px;border-radius:999px;background:var(--brand);color:var(--brand-ink);font-weight:700;font-size:1rem;line-height:1;font-family:var(--font-mono)}",
    ".delta{display:flex;width:max-content;align-items:center;gap:6px;margin-top:5px;padding:3px 8px;border-radius:6px;background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--warn-text);font-size:.76rem;font-weight:700;white-space:nowrap}",
    ".delta::before{content:'';width:7px;height:7px;border-radius:50%;background:var(--warn);flex:none}",
    ".delta .delta-scores{font-family:var(--font-mono)}",
    "@media (prefers-reduced-motion:reduce){.tab,summary,.bet-card{transition:none}}",
    ".score-dual{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}",
    ".score-chip-real{background:var(--ok);font-size:.86rem;min-width:88px}",
    ".score-chip-prono{background:var(--slate);font-size:.86rem;min-width:98px}",
    ".prob-bar{display:flex;height:6px;border-radius:999px;overflow:hidden;background:var(--track);margin:2px 0 4px}",
    ".prob-seg{display:block;height:100%}",
    ".prob-seg+.prob-seg{border-left:1px solid var(--surface)}",
    ".prob-seg.home{background:var(--brand)}",
    ".prob-seg.draw{background:var(--neutral)}",
    ".prob-seg.away{background:var(--away)}",
    ".prob-legend{display:flex;gap:12px;font-size:.74rem;color:var(--muted)}",
    ".prob-legend strong{color:var(--text);font-family:var(--font-mono)}",
    ".flag{font-size:1.05rem}",
    ".tiny{font-size:.76rem;color:var(--muted)}",
    ".cell-saisi{white-space:nowrap;text-align:center}",
    ".done-toggle{width:22px;height:22px;accent-color:var(--brand);cursor:pointer}",
    "tr.done-row .cell-meta,tr.done-row .cell-teams,tr.done-row .cell-prono,tr.done-row .cell-nutri,tr.done-row .cell-prob{opacity:.45}",
    "details{border:0;background:transparent}",
    "summary{cursor:pointer;font-size:.84rem;color:var(--brand);font-weight:700;display:inline-block;padding:6px 4px;border-radius:6px}",
    "summary:hover{text-decoration:underline}",
    "summary::marker{color:var(--brand)}",
    ".note-list{margin:8px 0 0;padding:8px 10px 8px 24px;color:var(--muted);font-size:.8rem;line-height:1.3;background:var(--surface-3);border:1px solid var(--line);border-radius:10px}",
    ".cell-details{position:relative}",
    ".cell-details details[open] .note-list{position:absolute;right:4px;top:calc(100% - 6px);width:560px;max-width:72vw;z-index:30;background:var(--surface);box-shadow:var(--shadow-floating)}",
    ".muted{color:var(--muted);font-size:.9rem}",
    ".err{background:var(--alert);color:#fff;padding:11px 12px;border-radius:10px;margin-bottom:10px}",
    ".err a{color:#fff;font-weight:700}",
    ".legend{margin-top:8px;color:var(--muted);font-size:.82rem;max-width:75ch}",
    ".health-pill{display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:5px 10px;font-size:.78rem;font-weight:700;border:1px solid transparent}",
    ".health-dot{display:inline-block;width:8px;height:8px;border-radius:50%}",
    ".health-good{background:var(--ok-bg);color:var(--ok);border-color:var(--ok-line)}",
    ".health-good .health-dot{background:var(--ok)}",
    ".health-warning{background:var(--warn-bg);color:var(--warn-text);border-color:var(--warn-line)}",
    ".health-warning .health-dot{background:var(--warn)}",
    ".health-critical{background:var(--alert-bg);color:var(--alert);border-color:var(--alert-line)}",
    ".health-critical .health-dot{background:var(--alert)}",
    ".guard-msg{margin-top:10px;padding:9px 10px;border-radius:10px;border:1px dashed var(--warn-line);background:var(--warn-bg);color:var(--warn-text);font-size:.84rem}",
    ".info-grid{display:grid;grid-template-columns:repeat(2,minmax(240px,1fr));gap:10px;margin-top:8px}",
    ".info-card{border:1px solid var(--line);border-radius:10px;background:var(--surface-3);padding:10px}",
    ".info-card h4{margin:0 0 6px;font-size:.88rem}",
    ".info-list{margin:0;padding-left:17px;color:var(--muted);font-size:.82rem;line-height:1.35}",
    ".info-line{font-size:.82rem;color:var(--muted);margin:2px 0}",
    ".status-line{display:flex;align-items:center;gap:10px;flex-wrap:wrap}",
    ".status-caption{color:var(--muted);font-size:.82rem}",
    ".tabbar{position:sticky;top:0;z-index:50;display:flex;gap:4px;background:var(--bg);padding:8px 4px 0;margin:0 0 14px;border-bottom:1px solid var(--line);box-shadow:0 8px 12px -12px rgba(20,30,50,.5)}",
    ".tab{text-decoration:none;padding:10px 16px;font-weight:700;font-size:.9rem;color:var(--muted);border-bottom:2px solid transparent;border-radius:9px 9px 0 0;line-height:1;transition:color .15s ease,background .15s ease,border-color .15s ease}",
    ".tab:hover{color:var(--brand);background:var(--brand-soft)}",
    ".tab.active{color:var(--brand);border-bottom-color:var(--brand);background:var(--surface)}",
    ".bankroll-form{display:flex;align-items:flex-end;gap:8px;margin-top:10px;flex-wrap:wrap}",
    ".bankroll-form .field{display:flex;flex-direction:column;gap:4px}",
    ".bankroll-form label{font-size:.78rem;font-weight:700;color:var(--muted)}",
    ".bankroll-form input{width:120px;padding:9px 10px;border:1px solid var(--line-2);border-radius:8px;font-size:.95rem;background:var(--surface);color:var(--text)}",
    ".bankroll-form button{padding:10px 14px;border:0;border-radius:8px;background:var(--brand);color:var(--brand-ink);font-weight:700;font-size:.85rem;cursor:pointer}",
    ".bankroll-form button:hover{background:var(--brand-dark)}",
    ".diag-wrap{margin-top:20px}",
    ".diag-wrap>summary{font-size:.85rem}",
    ".diag-wrap[open]>summary{margin-bottom:10px}",
    "@media (max-width:860px){.info-grid{grid-template-columns:1fr}}",
    "@media (max-width:760px){.wrap{padding:14px 10px 20px}.panel{padding:11px 10px}.tab{padding:13px 16px;font-size:.92rem}"
    ".md-title{position:static;margin:-11px -10px 4px;padding:10px 10px 8px}"
    "table,tbody{display:block;width:100%}thead{display:none}"
    "tr{display:block;border-top:1px solid var(--line);padding:10px 2px}"
    "td{display:block;border:0;padding:2px 0;width:auto}"
    ".cell-meta{display:flex;align-items:baseline;gap:8px}"
    ".cell-meta .kick{display:inline}"
    ".meta-sub{display:inline;margin:0;white-space:normal}"
    ".cell-teams{font-size:.95rem}"
    ".cell-prono,.cell-nutri{display:inline-block;vertical-align:middle;margin:4px 10px 0 0}"
    ".cell-prob{margin-top:4px}"
    ".cell-saisi{display:inline-block;vertical-align:middle;margin:8px 16px 0 0;text-align:left}"
    ".cell-saisi::before{content:'Saisi';color:var(--muted);font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;margin-right:8px}"
    ".cell-details{display:inline-block;vertical-align:middle;margin-top:8px}"
    ".cell-details details[open] .note-list{position:static;width:auto;max-width:none;box-shadow:none}"
    ".done-toggle{width:24px;height:24px}summary{padding:10px 4px}}",
])


def _render_header(safe_tab: str, health: Optional[Dict], health_meta: Dict[str, str],
                   n_future: int, n_past: int, n_changed: int = 0) -> List[str]:
    subtitle = ("Recommandations prudentes calculées à partir du modèle et des cotes bookmaker."
                if safe_tab == "paris"
                else "Vue calendrier rapide : ouvrez un match pour voir les explications utiles à la décision.")
    parts = [
        "<header class='mast'>",
        "<div>",
        "<h1>Pronos Coupe du Monde 2026</h1>",
        f"<p class='subtitle'>{subtitle}</p>",
        "</div>",
        "<div class='status-line'>",
    ]
    # Le détail qualité/solidité vit dans le panneau Diagnostics ; le header ne
    # signale que l'anomalie (feu non vert) et les compteurs utiles.
    if (health or {}).get("level") != "good":
        parts.append(
            f"<div class='health-pill {health_meta['class']}'><span class='health-dot'></span>"
            f"Feu data : {health_meta['label']} ({health_meta['state']})</div>"
        )
    parts.extend([
        "<div class='stats'>",
        f"<span class='stamp'>Futurs {n_future}</span>",
        f"<span class='stamp'>Passés {n_past}</span>",
        "<span class='stamp' id='done-count' aria-live='polite'>Saisis : 0</span>",
    ])
    if n_changed:
        parts.append(
            f"<span class='stamp stamp-warn' title='Pronos recalculés après mise à jour des données — repérez les badges Modifié'>"
            f"Modifiés : {n_changed}</span>"
        )
    parts.extend([
        "</div>",
        "</div>",
        "</header>",
    ])
    return parts


def _render_diagnostics(health: Optional[Dict], health_meta: Dict[str, str],
                        solidity_report: Optional[Dict], data_info: Optional[Dict]) -> List[str]:
    parts: List[str] = []
    if health:
        level_label = {
            "good": "Bon",
            "warning": "À surveiller",
            "critical": "Critique",
        }.get(health.get("level"), "Inconnu")
        parts.extend([
            "<div class='panel'>",
            f"<strong>Qualité des données : {health.get('score')}/100 ({level_label})</strong> ",
            f"<span class='health-pill {health_meta['class']}' style='margin-left:8px'><span class='health-dot'></span>{health_meta['label']}</span>",
            "<details style='margin-top:8px'><summary>Pourquoi ce score ?</summary><ul class='note-list'>",
            f"<li>Dates manquantes : {health.get('fixtures_missing_dates', 0)}</li>",
            f"<li>Matchs passés sans score final : {health.get('fixtures_past_without_score', 0)}</li>",
            f"<li>Âge ratings (jours) : {health.get('ratings_age_days')}</li>",
            f"<li>Âge signaux équipes (jours) : {health.get('status_age_days')}</li>",
        ])
        if not health.get("alerts"):
            parts.append("<li>Aucune alerte : les données sont cohérentes pour l'analyse actuelle.</li>")
        for a in health.get("alerts", []):
            parts.append(f"<li>{html.escape(a)}</li>")
        parts.append("</ul></details>")

        if data_info:
            quality_map = {
                "good": "Bon",
                "warning": "À surveiller",
                "critical": "Critique",
            }
            q_score = (data_info.get("quality_rating") or {}).get("score")
            q_level = quality_map.get((data_info.get("quality_rating") or {}).get("level"), "Inconnu")
            status_cov = (data_info.get("other") or {}).get("status_coverage_pct")
            home_adv_cov = (data_info.get("other") or {}).get("home_adv_coverage_pct")
            status_cov_txt = "n/a" if status_cov is None else f"{round(status_cov * 100)}%"
            home_adv_cov_txt = "n/a" if home_adv_cov is None else f"{round(home_adv_cov * 100)}%"

            parts.extend([
                "<details style='margin-top:8px'><summary>Info données (sources + fraîcheur)</summary>",
                "<div class='info-grid'>",
                "<section class='info-card'>",
                "<h4>Sources de données</h4>",
                "<ul class='info-list'>",
            ])
            for row in data_info.get("data_sources", []):
                parts.append(f"<li>{html.escape(str(row))}</li>")
            parts.extend([
                "</ul>",
                "</section>",
                "<section class='info-card'>",
                "<h4>Sources d'information</h4>",
                "<ul class='info-list'>",
            ])
            for row in data_info.get("information_sources", []):
                parts.append(f"<li>{html.escape(str(row))}</li>")
            parts.extend([
                "</ul>",
                "</section>",
                "<section class='info-card'>",
                "<h4>Date de dernière mise à jour</h4>",
                f"<div class='info-line'>ratings.as_of : {html.escape(str((data_info.get('last_updates') or {}).get('ratings_as_of')))}</div>",
                f"<div class='info-line'>team_status.as_of : {html.escape(str((data_info.get('last_updates') or {}).get('team_status_as_of')))}</div>",
                f"<div class='info-line'>dernier snapshot prédiction : {html.escape(str((data_info.get('last_updates') or {}).get('latest_prediction_snapshot')))}</div>",
                "</section>",
                "<section class='info-card'>",
                "<h4>Qualité + infos pertinentes</h4>",
                f"<div class='info-line'>Qualité des données : {html.escape(str(q_score))}/100 ({html.escape(q_level)})</div>",
                f"<div class='info-line'>Ratings live : {html.escape(str((data_info.get('other') or {}).get('live_ratings', 0)))}/{html.escape(str((data_info.get('other') or {}).get('ratings_total', 0)))}</div>",
                f"<div class='info-line'>Ratings estimés : {html.escape(str((data_info.get('other') or {}).get('estimated_ratings', 0)))}</div>",
                f"<div class='info-line'>Couverture team status : {html.escape(status_cov_txt)}</div>",
                f"<div class='info-line'>Couverture home_adv : {html.escape(home_adv_cov_txt)}</div>",
                f"<div class='info-line'>Matchs complétés : {html.escape(str((data_info.get('other') or {}).get('fixtures_completed', 0)))}/{html.escape(str((data_info.get('other') or {}).get('fixtures_total', 0)))}</div>",
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
            f"<strong>Solidité du système : {score_text}/100 ({level_label})</strong>",
            "<details style='margin-top:8px'><summary>Comment ce score est calculé ?</summary><ul class='note-list'>",
            f"<li>Matchs évalués : {solidity_report.get('matches', 0)}</li>",
            f"<li>Précision 1N2 : {('n/a' if solidity_report.get('result_accuracy') is None else str(round(solidity_report.get('result_accuracy') * 100)) + '%')}</li>",
            f"<li>Score exact touché : {('n/a' if solidity_report.get('exact_score_hit') is None else str(round(solidity_report.get('exact_score_hit') * 100)) + '%')}</li>",
            f"<li>Brier 1N2 (plus bas = mieux) : {('n/a' if solidity_report.get('brier_1x2') is None else format(solidity_report.get('brier_1x2'), '.3f'))}</li>",
            f"<li>Log-loss 1N2 (plus bas = mieux) : {('n/a' if solidity_report.get('logloss_1x2') is None else format(solidity_report.get('logloss_1x2'), '.3f'))}</li>",
            f"<li>RPS 1N2 (standard du domaine, plus bas = mieux) : {('n/a' if solidity_report.get('rps_1x2') is None else format(solidity_report.get('rps_1x2'), '.3f'))}</li>",
            f"<li>Confiance moyenne des picks : {('n/a' if solidity_report.get('avg_pick_conf') is None else str(round(solidity_report.get('avg_pick_conf') * 100)) + '%')}</li>",
        ])
        if solidity_report.get("calibration_gap") is not None:
            parts.append(
                f"<li>Écart calibration (confiance - précision) : {(solidity_report.get('calibration_gap') * 100):+.1f} point(s)</li>"
            )
        else:
            parts.append("<li>Écart calibration (confiance - précision) : n/a</li>")
        buckets = solidity_report.get("confidence_buckets") or []
        if buckets:
            parts.append("<li>Calibration par tranche de confiance :</li>")
            for b in buckets:
                parts.append(
                    f"<li>{b['range']} | n={b['count']} | hit {round(b['hit_rate'] * 100)}% | conf {round(b['avg_conf'] * 100)}% | gap {(b['gap'] * 100):+.1f}pt</li>"
                )
        else:
            parts.append("<li>Calibration par tranche de confiance : n/a (aucun match terminé)</li>")
        for a in solidity_report.get("alerts", []):
            parts.append(f"<li>{html.escape(a)}</li>")
        parts.extend(["</ul></details>", "</div>"])

    return parts


def _render_paris(rec: Optional[Dict], bankroll: float, bet_blocked: bool) -> List[str]:
    bk = (rec.get("bankroll") if rec else bankroll) or bankroll
    parts = [
        "<section class='panel'>",
        "<h2 style='margin:0 0 4px'>Recommandations de paris — stratégie prudente</h2>",
        "<p class='subtitle'>Sélection calculée automatiquement : uniquement de la <strong>value</strong> "
        "(le modèle bat la cote dé-marginée), probabilités <strong>ramenées vers le marché</strong> pour "
        "corriger l'excès de confiance, mises en <strong>quart-Kelly plafonnées</strong>, combinés limités "
        "à <strong>2 sélections</strong>.</p>",
        "<form method='get' class='bankroll-form'>",
        "<input type='hidden' name='tab' value='paris'>",
        "<div class='field'><label for='bankroll'>Bankroll (€)</label>",
        f"<input id='bankroll' name='bankroll' type='number' min='1' max='100000' step='1' value='{bk:.0f}' inputmode='numeric'></div>",
        "<button type='submit'>Recalculer les mises</button>",
        "</form>",
        _odds_source_note(),
        "</section>",
    ]

    if bet_blocked:
        parts.append("<div class='panel'><div class='muted'>Recommandations indisponibles : qualité des données critique. Mettez à jour fixtures, ratings et team_status.</div></div>")
        return parts
    if not rec:
        parts.append("<div class='panel'><div class='muted'>Aucun match à venir : rien à parier pour l'instant.</div></div>")
        return parts

    if rec["n_with_odds"] == 0:
        # Pas de cotes : aucune analyse n'a pu tourner — un seul état vide qui
        # guide vers l'action, plutôt que des stats à zéro contradictoires.
        parts.extend([
            "<div class='panel'>",
            "<strong>Aucune cote bookmaker chargée.</strong>",
            "<p class='muted' style='margin:6px 0 0'>Les recommandations comparent le modèle aux cotes du marché : "
            "sans cotes, aucune value n'est calculable. Connectez une source de cotes gratuite (The Odds API) "
            "pour activer cette page.</p>",
            "<details style='margin-top:8px'><summary>Comment connecter les cotes ?</summary><ul class='note-list'>",
            "<li>Créez une clé gratuite sur the-odds-api.com.</li>",
            "<li>Renseignez-la dans la variable d'environnement <code>ODDS_API_KEY</code> ou le fichier <code>data/odds_api_key.txt</code>.</li>",
            "<li>Rechargez cette page : les cotes se récupèrent automatiquement dès leur publication.</li>",
            "</ul></details>",
            "</div>",
        ])
        return parts

    parts.extend([
        "<div class='panel'>",
        "<div class='stats'>",
        f"<div class='stamp'>Matchs analysés : {rec['n_future']}</div>",
        f"<div class='stamp'>Avec cotes : {rec['n_with_odds']}</div>",
        f"<div class='stamp'>Paris simples value : {len(rec['singles'])}</div>",
        f"<div class='stamp'>Combinés : {len(rec['combos'])}</div>",
        f"<div class='stamp'>Mise totale : {_eur(rec['total_stake'], 2)}</div>",
        f"<div class='stamp'>Gain attendu (modèle) : {_eur_signed(rec['ev_profit'])}</div>",
        "</div>",
        "<div class='legend'>Le \"gain attendu\" est l'espérance du modèle : fiable seulement dans la mesure où le modèle est bien calibré (il a tendance à être trop confiant). Misez petit.</div>",
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
            # Ordre du ticket Winamax : sélection + cote, contexte, mise, retour
            # — la recopie se fait position à position, le calcul passe en détail.
            parts.extend([
                "<article class='bet-card'>",
                f"<div class='bet-sel-line'>{html.escape(sel)} <span class='bet-odds'>@ {b['odds']:.2f}</span></div>",
                f"<div class='bet-context'>1N2 &middot; {html.escape(s['label'])}"
                + (f" &middot; {html.escape(s['when'])}" if s.get("when") else "")
                + "</div>",
                f"<div class='bet-stake-line'><span class='bet-stake'>Miser {_eur(s['stake'], 2)}</span> "
                f"<span class='bet-return'>retour si gagné ~{_eur(ret, 2)}</span></div>",
                "<details class='bet-why'><summary>Détail du calcul</summary><ul class='note-list'>",
                f"<li>Modèle {round(b['model']*100)}% &rarr; ajusté {round(b['shrunk']*100)}% "
                f"(juste marché {round(b['fair']*100)}%)</li>",
                f"<li>Avantage +{round(b['edge']*100)} pt &middot; EV {b['ev']*100:+.1f}%</li>",
                "</ul></details>",
                "</article>",
            ])
    else:
        parts.append("<div class='muted'>Aucune value détectée — ne pas parier ce créneau (c'est fréquent, et c'est sain).</div>")
    parts.extend(["</div>", "</section>"])

    parts.extend([
        "<section class='panel'>",
        "<h3 style='margin:0'>Combinés (2 sélections max &middot; mise minime)</h3>",
        "<div class='bet-grid'>",
    ])
    if rec["combos"]:
        for c in rec["combos"]:
            ret = c["stake"] * c["combined_odds"]
            parts.append("<article class='bet-card'>")
            parts.append(
                f"<div class='bet-sel-line'>Combiné {len(c['legs'])} sélections "
                f"<span class='bet-odds'>@ {c['combined_odds']:.2f}</span></div>"
            )
            for idx, leg in enumerate(c["legs"], start=1):
                pair = _split_match(leg["label"]) or (leg["label"], "")
                sel_txt = _sel_fr(leg["sel"], pair[0], pair[1])
                parts.append(
                    f"<div class='bet-context'>{idx}. <strong>{html.escape(sel_txt)}</strong> "
                    f"<span class='bet-odds'>@ {leg['odds']:.2f}</span> &middot; {html.escape(leg['label'])}</div>"
                )
            parts.append(
                f"<div class='bet-stake-line'><span class='bet-stake'>Miser {_eur(c['stake'], 2)}</span> "
                f"<span class='bet-return'>retour si gagné ~{_eur(ret, 2)}</span></div>"
            )
            parts.append(
                "<details class='bet-why'><summary>Détail du calcul</summary><ul class='note-list'>"
                f"<li>EV {c['ev']*100:+.1f}% &middot; proba modèle {round(c['combined_prob']*100)}%</li>"
                "</ul></details>"
            )
            parts.append("</article>")
    else:
        parts.append("<div class='muted'>Aucun combiné ne passe le filtre prudent — sautez les combinés (ils ont perdu ~69% au backtest WC2022).</div>")
    parts.extend(["</div>", "</section>"])

    return parts


def _render_row(r: Dict) -> List[str]:
    est = " *" if r["est"] else ""
    match_ref = f"{r['id']}|{r['home']}|{r['away']}|{r['date']}"
    home_label = r["home_label"]
    away_label = r["away_label"]

    ph, pd, pa = r["p_home"], r["p_draw"], r["p_away"]
    mx = max(ph, pd, pa)
    leg_home = f"<strong>1 {ph}%</strong>" if ph == mx else f"1 {ph}%"
    leg_draw = f"<strong>N {pd}%</strong>" if pd == mx else f"N {pd}%"
    leg_away = f"<strong>2 {pa}%</strong>" if pa == mx else f"2 {pa}%"
    prob_block = (
        f"<div class='prob-bar' role='img' aria-label='Probabilités 1 {ph}%, nul {pd}%, 2 {pa}%'>"
        f"<span class='prob-seg home' style='width:{ph}%'></span>"
        f"<span class='prob-seg draw' style='width:{pd}%'></span>"
        f"<span class='prob-seg away' style='width:{pa}%'></span>"
        f"</div>"
        f"<div class='prob-legend'><span>{leg_home}</span><span>{leg_draw}</span><span>{leg_away}</span></div>"
    )
    nutri_chip = (
        f"<span class='nutri nutri-{html.escape(r['nutri'].lower())}' "
        f"title='Indice de confiance {html.escape(r['nutri'])} (A = forte, E = faible)' "
        f"aria-label='Confiance {html.escape(r['nutri'])} sur A à E'>{html.escape(r['nutri'])}</span>"
    )

    delta_badge = ""
    if not r["completed"] and r.get("prediction_changed"):
        delta_badge = (
            f"<span class='delta' role='status' "
            f"title='Prono recalculé après une maj des données — la coche Saisi vaut acquittement'>"
            f"Modifié <span class='delta-scores'>{html.escape(r['predicted_score'])} &rarr; "
            f"{html.escape(r['predicted_score_live'])}</span></span>"
        )
    if r["completed"]:
        score_block = (
            f"<span class='score-dual'>"
            f"<span class='score-chip score-chip-real'>Réel {html.escape(r['actual_score'] or r['score'])}</span>"
            f"<span class='score-chip score-chip-prono'>Prono {html.escape(r['predicted_score'])}</span>"
            f"</span>"
        )
    else:
        # Le mot « Prono » est porté par l'en-tête de colonne — chip = score seul.
        score_block = (
            f"<span class='score-chip score-chip-prono'>{html.escape(r['score'])}</span>"
        )

    kick = r.get("kickoff_paris") or ""
    kick_html = (f"<span class='kick'>{html.escape(kick)}</span>" if kick
                 else "<span class='kick kick-tbd'>&mdash;</span>")
    meta_sub = (f"J{html.escape(str(r['matchday']))} · Gr. {html.escape(str(r['group']))}"
                f" · {html.escape(str(r['id']))}")

    parts = ["<tr>"]
    parts.append(f"<td class='cell-meta'>{kick_html}<span class='meta-sub'>{meta_sub}</span></td>")
    parts.append(
        f"<td class='cell-teams'>"
        f"<span class='flag'>{r['home_flag']}</span> <span class='team-name'>{html.escape(home_label)}</span>"
        f"<span class='team-sep'>&ndash;</span>"
        f"<span class='team-name'>{html.escape(away_label)}</span> <span class='flag'>{r['away_flag']}</span>"
        f"</td>"
    )
    parts.append(f"<td class='cell-prono'>{score_block}{delta_badge}</td>")
    parts.append(f"<td class='cell-nutri'>{nutri_chip}</td>")
    parts.append(f"<td class='cell-prob'>{prob_block}</td>")
    parts.append(
        f"<td class='cell-saisi'><input class='done-toggle' type='checkbox' "
        f"aria-label='Marquer {html.escape(home_label)} vs {html.escape(away_label)} comme saisi sur Mon Petit Prono' "
        f"title='Cochez quand vous avez saisi ce prono sur Mon Petit Prono' "
        f"data-match='{html.escape(match_ref)}'></td>"
    )

    parts.append("<td class='cell-details'><details><summary>Détails</summary><ul class='note-list'>")
    parts.append(
        f"<li>Prono recommandé (optimise les points Mon Petit Prono) : {html.escape(r['predicted_score'])} ({r['score_conf']}%)</li>"
    )
    if r["mpp_differs"]:
        parts.append(
            f"<li>Score le plus probable du modèle : {html.escape(r['mpp_modal_score'])}</li>"
        )
    parts.append(
        f"<li>Choix 1N2 le plus probable : {html.escape(r['pick_label'])} ({round(r['pick_prob'] * 100)}%), indice {html.escape(r['nutri'])}</li>"
    )
    parts.append(
        f"<li>Recommandation de pari actuelle : {html.escape(r['bet'])} ({r['bet_conf']}%{est})</li>"
    )
    if r.get("prediction_changed"):
        parts.append(
            f"<li><strong>● Prono mis à jour</strong> : le prono figé était "
            f"{html.escape(r['predicted_score'])}, le modèle estime maintenant "
            f"{html.escape(r['predicted_score_live'])} après une maj des données "
            f"(ratings / forme / blessures / avantage hôte / attaque-défense).</li>"
        )
    if r["completed"]:
        parts.append(f"<li>Prono conservé : {html.escape(r['predicted_score'])}</li>")
        if not r.get("prediction_saved"):
            parts.append(f"<li>Note : prono non figé (estimation actuelle : {html.escape(r['predicted_score_live'])}).</li>")
    if r["odds"]:
        parts.append(
            f"<li>Cotes bookmaker chargées : 1 {r['odds'][0]:.2f} / N {r['odds'][1]:.2f} / 2 {r['odds'][2]:.2f}</li>"
        )
    for vs in r["value_summaries"]:
        parts.append(f"<li>{html.escape(vs)}</li>")
    for note in r["notes"]:
        parts.append(f"<li>{html.escape(note)}</li>")
    parts.append("</ul></details></td>")
    parts.append("</tr>")
    return parts


def _render_page(rows: List[Dict], recommendations: Optional[Dict], error: str = "",
                 tab: str = "futurs", health: Optional[Dict] = None,
                 solidity_report: Optional[Dict] = None, data_info: Optional[Dict] = None,
                 bankroll: float = 50.0) -> bytes:
    safe_tab = tab if tab in _TAB_LABELS else "futurs"

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
        f"<title>Pronos CM2026 — {_TAB_LABELS[safe_tab]}</title>",
        "<style>",
        _CSS,
        "</style></head><body><main class='wrap'>",
    ]
    n_changed = sum(1 for r in future_rows if r.get("prediction_changed"))
    parts.extend(_render_header(safe_tab, health, health_meta, len(future_rows), len(past_rows), n_changed))

    if error:
        parts.append(
            f"<div class='err' role='alert'>{html.escape(error)} "
            "<a href='/?tab=futurs'>Voir tous les matchs</a></div>"
        )

    def _tab(key: str, label: str) -> str:
        active = " active" if safe_tab == key else ""
        current = " aria-current='page'" if safe_tab == key else ""
        return f"<a href='/?tab={key}' class='tab{active}'{current}>{label}</a>"

    parts.extend([
        "<nav class='tabbar' aria-label='Sections'>",
        _tab("futurs", "Futurs"),
        _tab("passes", "Passés"),
        _tab("paris", "Paris"),
        "</nav>",
    ])
    if (health or {}).get("level") != "good":
        parts.append(f"<div class='guard-msg' style='margin-top:0'>{html.escape(health_meta['message'])}</div>")
    if safe_tab != "paris" and shown_rows:
        parts.append(
            "<p class='legend' style='margin:0 0 12px'>Indice de confiance du pronostic : "
            "<strong>A</strong> forte &rarr; <strong>E</strong> faible. La barre indique les "
            "probabilités <strong>1</strong> (domicile) · <strong>N</strong> (nul) · <strong>2</strong> (extérieur). "
            "Un badge <strong>Modifié</strong> signale un prono recalculé après mise à jour des données — "
            "cocher Saisi vaut acquittement.</p>"
        )

    if safe_tab == "paris":
        parts.extend(_render_paris(recommendations, bankroll, bet_blocked))

    if not shown_rows and safe_tab != "paris":
        if safe_tab == "passes":
            parts.append(
                "<div class='panel'><div class='muted'>Aucun match joué pour l'instant : les résultats "
                "apparaîtront ici après les premiers coups d'envoi. "
                "<a href='/?tab=futurs'>Voir les matchs à venir</a></div></div>"
            )
        else:
            parts.append(
                "<div class='panel'><div class='muted'>Aucun match à venir à afficher. "
                "<a href='/?tab=passes'>Voir les matchs joués</a></div></div>"
            )

    for day, md_rows in grouped:
        day_label = _fr_date_label(day)
        if safe_tab == "futurs":
            day_count = (f"<span class='tiny'>{len(md_rows)} matchs · "
                         f"<span class='day-saisis'>0/{len(md_rows)} saisis</span></span>")
        else:
            day_count = f"<span class='tiny'>{len(md_rows)} matchs</span>"
        parts.extend([
            "<section class='panel'>",
            "<div class='md-title'>",
            f"<h2>{html.escape(day_label)}</h2>",
            day_count,
            "</div>",
            "<table><thead><tr>",
            "<th style='width:11%'>Heure (FR)</th><th style='width:28%'>Match</th>"
            "<th style='width:16%'>Pronostic</th><th style='width:6%'>Conf.</th>"
            "<th style='width:20%'>Probabilités 1 · N · 2</th><th style='width:7%'>Saisi</th>"
            "<th style='width:12%'>Détails</th>",
            "</tr></thead><tbody>",
        ])
        for r in md_rows:
            parts.extend(_render_row(r))
        parts.extend(["</tbody></table>", "</section>"])

    diag_chunk = _render_diagnostics(health, health_meta, solidity_report, data_info)
    if diag_chunk:
        parts.append("<details class='diag-wrap'><summary>Diagnostics — qualité des données &amp; solidité du modèle</summary>")
        parts.extend(diag_chunk)
        parts.append("</details>")

    parts.extend([
        "<script>",
        "(function(){",
        "const key='wc2026_done_predictions_v1';",
        "const countEl=document.getElementById('done-count');",
        "const parse=()=>{try{return new Set(JSON.parse(localStorage.getItem(key)||'[]'));}catch(_){return new Set();}};",
        "const save=(set)=>localStorage.setItem(key,JSON.stringify(Array.from(set)));",
        "const refreshCount=(set)=>{if(countEl){countEl.textContent='Saisis : '+set.size;}};",
        "const refreshDays=()=>{document.querySelectorAll('.day-saisis').forEach((el)=>{",
        "const sec=el.closest('section');if(!sec){return;}",
        "const boxes=sec.querySelectorAll('.done-toggle');let n=0;",
        "boxes.forEach((b)=>{if(b.checked){n++;}});",
        "el.textContent=n+'/'+boxes.length+' saisis';});};",
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
        "save(done);refreshCount(done);refreshDays();",
        "});",
        "});",
        "refreshCount(done);refreshDays();",
        "})();",
        "</script>",
        "</main></body></html>",
    ])
    return "".join(parts).encode("utf-8")


def handle_request(params: Dict[str, str]) -> bytes:
    """Pipeline partagé (parsing des paramètres + moteur + rendu).

    Utilisé tel quel par le serveur stdlib local et par le wrapper Flask/Vercel,
    pour que les deux entrées restent strictement identiques."""
    matchday = (params.get("matchday") or "").strip()
    date_value = (params.get("date") or "").strip()
    odds_file = (params.get("odds_file") or "").strip()
    action = (params.get("action") or "").strip().lower()
    tab = (params.get("tab") or "futurs").strip().lower() or "futurs"
    if action == "reco":          # back-compat: old reco button -> Paris page
        tab = "paris"
    no_auto = (params.get("no_auto") or "") in ("1", "on", "true")
    try:
        bankroll = float((params.get("bankroll") or "50").strip())
    except ValueError:
        bankroll = 50.0
    if not math.isfinite(bankroll) or bankroll <= 0 or bankroll > 100_000:
        bankroll = 50.0

    error = ""
    if date_value:
        try:
            _parse_date(date_value)
        except ValueError:
            error = f"Date invalide « {date_value} » : utilisez le format AAAA-MM-JJ (ex. 2026-06-15)."
            date_value = ""

    rows: List[Dict] = []
    recommendations = None
    health = None
    solidity_report = None
    data_info = None

    try:
        try:
            autonomous.autonomous_refresh()
        except Exception:
            pass  # best-effort : une maj ratée ne doit jamais bloquer la page
        fixtures = data.load_fixtures()
        _apply_paris_kickoffs(fixtures)   # show France (Europe/Paris) dates, not US dates
        # Two separate loads on purpose: the pipeline below mutates `ratings`,
        # while the solidity assessment needs the untouched on-disk baseline.
        base_ratings = data.load_ratings()
        ratings = data.load_ratings()
        ratings, _ = live_ratings.ensure(ratings)   # keep Elo fresh on read-only hosts (Vercel)
        team_status = data.load_team_status()
        solidity_report = solidity.assess_model_solidity(fixtures, base_ratings)
        if not no_auto:
            ratings, _ = updater.apply_completed_results(ratings, fixtures)
        ratings = team_signals.adjust_ratings_with_status(ratings, team_status)
        ratings = expert_signals.apply_expert_priors(ratings)
        health = data_quality.assess_data_health(fixtures, ratings, team_status)

        selected = _select_fixtures(fixtures, date_value, matchday)
        if not selected and not error:
            if date_value:
                error = f"Aucun match le {date_value}."
            elif matchday:
                error = f"Aucun match pour la journée {matchday}."
        if odds_file:                                  # manual override (advanced)
            odds_board = _load_odds_board(odds_file)
        elif tab == "paris":                           # betting page: auto-fetch (cooldown + credit-capped)
            odds_board = odds_fetch.ensure_board(ratings, fixtures)
        else:                                          # other tabs: read cache only, never spend credits
            odds_board = odds_fetch.load_cached_board()
        # Après le chargement des cotes : un odds_file rejeté ne doit pas
        # apparaître comme « source de données » dans les diagnostics.
        data_info = _build_data_info(fixtures, ratings, team_status, health, odds_file)
        rows = _analyse_rows(selected, ratings, odds_board, team_status=team_status)
        if tab == "paris" and (health or {}).get("level") != "critical":
            recommendations = _build_recommendations(rows, bankroll=bankroll)
    except UiError as exc:
        error = str(exc)          # message métier déjà rédigé pour l'utilisateur
    except Exception:
        traceback.print_exc()     # détail côté serveur uniquement
        error = "Une erreur interne est survenue pendant la préparation de la page. Réessayez dans un instant."

    return _render_page(rows, recommendations, error=error, tab=tab, health=health,
                        solidity_report=solidity_report, data_info=data_info, bankroll=bankroll)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        flat = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        body = handle_request(flat)
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
