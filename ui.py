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

from engine import autonomous, betting, calibration, common, data, data_quality, expert_signals, live_ratings, mpp, odds as oddsmod, odds_fetch, prediction, solidity, strategies, team_signals, updater

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
    the kickoff time — the jetlag fix, so a US-evening game shows on the next day
    like it does in France. Adds kickoff_paris (HH:MM).

    The kickoff comes from the live odds feed when available, else from the
    fixture's own committed ``kickoff_utc`` (so dates/times are correct even with
    no feed — e.g. on a deploy without an odds key). Matches with no known
    kickoff keep their stored date."""
    kicks = odds_fetch.load_kickoffs()
    for m in fixtures:
        ct = kicks.get(str(m.get("id", "")).upper()) or m.get("kickoff_utc")
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


# Verdict confiance/risque d'un match, dérivé de la distribution 1N2. Sa raison
# d'être : la plupart des matchs ont un favori net (p_top médian ~74 %), donc
# « le favori gagne » n'apporte rien — la valeur est de pointer les matchs où le
# favori est FRAGILE pour ne PAS le miser. Quatre tiers, décision-orientés :
#   - solide : favori net, marge confortable → mise défendable
#   - serre  : favori, mais avantage mince → prudence
#   - piege  : favori d'une ÉQUIPE mais nul très probable → le piège classique
#   - ouvert : aucune issue ne se détache → pile ou face, à éviter
# Entrées en POURCENTAGES entiers (comme stockés sur la ligne). Fonction pure :
# c'est une aide à la décision de pari, donc testée (tests/test_confidence.py).
_VERDICT_LABELS = {
    "solide": "Favori solide",
    "serre": "Favori léger",
    "piege": "Piège : nul probable",
    "ouvert": "Pile ou face",
}


def _verdict_counts(rows: List[Dict]) -> Dict[str, int]:
    """Compte les verdicts confiance/risque sur un lot de matchs (à venir).
    Sert le bandeau récap : voir d'un coup combien de favoris sont solides
    (rien à décider) vs combien sont à examiner — c'est là que l'outil sert."""
    counts = {"solide": 0, "serre": 0, "piege": 0, "ouvert": 0}
    for r in rows:
        if r.get("p_home") is None:
            continue
        tier = _confidence_verdict(r["p_home"], r["p_draw"], r["p_away"])["tier"]
        counts[tier] += 1
    return counts


def _confidence_verdict(p_home: int, p_draw: int, p_away: int) -> Dict[str, str]:
    probs = {"1": int(p_home), "N": int(p_draw), "2": int(p_away)}
    pick = max(probs, key=lambda k: probs[k])
    top = probs[pick]
    second = sorted(probs.values(), reverse=True)[1]
    margin = top - second
    team_pick = pick in ("1", "2")

    if top < 45:
        tier, why = "ouvert", "aucune issue ne se détache — à éviter"
    elif team_pick and p_draw >= 30:
        tier, why = "piege", f"favori à {top}% mais nul à {p_draw}%"
    elif top >= 60 and margin >= 22:
        tier, why = "solide", "favori nettement devant"
    else:
        tier, why = "serre", "avantage mince — prudence"
    return {"tier": tier, "label": _VERDICT_LABELS[tier], "why": why}


def _pick_verdict(p_home: int, p_draw: int, p_away: int, pick_outcome: str) -> Dict[str, str]:
    """Verdict de la LIGNE = la DÉCISION réellement jouée (le pick MPP), pas un
    favori qu'on ne joue pas. Quand le pick suit le favori 1N2, c'est le tier de
    confiance (solide/léger/piège/pile ou face). Quand il diverge — favori trop
    court → on joue le nul, ou outsider sous-coté → on joue l'outsider — le
    verdict PORTE la décision, pour que verdict + score « prono 0-0 » + pastille
    Nutri racontent une seule histoire (le pick contrarian, peu probable mais
    payant), au lieu de « Favori solide » + « E » qui se lisent contradictoires
    (design-critic 2026-06-16)."""
    fav = max(("home", "draw", "away"),
              key=lambda o: {"home": p_home, "draw": p_draw, "away": p_away}[o])
    if pick_outcome == fav:
        return _confidence_verdict(p_home, p_draw, p_away)
    if pick_outcome == "draw":
        return {"tier": "nul", "label": "Jouer le nul",
                "why": "favori trop court — le nul rapporte plus de points au barème"}
    return {"tier": "valeur", "label": "Jouer l'outsider",
            "why": "outsider sous-coté — il rapporte plus de points au barème"}


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


def _best_selection(home_label: str, away_label: str, probs: Dict[str, float]) -> Tuple[str, str, float]:
    return max(
        (("home", f"Victoire {home_label}", probs["home"]),
         ("draw", "Match nul", probs["draw"]),
         ("away", f"Victoire {away_label}", probs["away"])),
        key=lambda x: x[2],
    )


def _analyse_rows(fixtures: List[Dict], ratings: Dict, odds_board: Dict[str, List[float]],
                  team_status: Optional[Dict] = None):
    rows = []
    expert_sources = expert_signals.load_sources()
    mpp_board = data.load_mpp_board()
    for m in fixtures:
        home = m["home"]
        away = m["away"]
        home_label = _team_label(home)
        away_label = _team_label(away)
        rh = ratings["teams"][home]
        ra = ratings["teams"][away]
        out = prediction.analyse_match(m, ratings)
        # Calibrated 1X2 = the honest confidence the whole page reads off (bar,
        # verdict, Nutri pastille, value EV). Temperature scaling is monotone, so
        # the favourite never flips; only the confidence is pulled toward honesty
        # (engine/calibration.py). The MPP scoreline (rec) stays on the raw grid.
        cal = calibration.calibrated_probs(out)
        pick_sel, pick_label, pick_prob = _best_selection(home_label, away_label, cal)

        (si, sj), sp = out["top_scores"][0]  # modal score (kept for the note below)
        est = rh.get("source") != "live" or ra.get("source") != "live"
        completed = _is_completed(m)
        actual_score = None
        if completed:
            actual_score = f"{m.get('actual_home')}-{m.get('actual_away')}"

        odds = _find_match_odds(m, odds_board)

        # MPP-optimal prono: the scoreline that maximises expected Mon Petit Prono
        # points. Base points come from the real MPP barème when known
        # (data/mpp_board.json, ask-Claude layer), else from the committed/cached
        # bookmaker odds (≈ cote×10) — points follow the cote, so a correct draw
        # pays ~2× a short favourite and the pick must value that, not just the
        # modal score. Same call (and same committed odds) as the freeze
        # (engine/prediction.scoreline) so displayed and frozen can't drift.
        mpp_points = mpp_board.get(str(m.get("id", "")).upper())
        knockout = mpp.is_knockout(m)
        rec = mpp.recommend(out, odds=odds, mpp_points=mpp_points, knockout=knockout)
        rsi, rsj = rec["score"]
        # The "gros lot" : highest-paying outcome the model still rates plausible —
        # the deliberate high-variance play for a trailing player (≠ the EV pick).
        upside = mpp.upside_pick(out, mpp_points, knockout=knockout) if mpp_points else None
        live_predicted_score = f"{rsi}-{rsj}"
        frozen_home = _as_int(m.get("predicted_home"))
        frozen_away = _as_int(m.get("predicted_away"))
        preserved_predicted_score = None
        if frozen_home is not None and frozen_away is not None:
            preserved_predicted_score = f"{frozen_home}-{frozen_away}"
        predicted_score = preserved_predicted_score or live_predicted_score
        # Verdict de justesse : seulement quand le match est joué ET qu'un prono
        # a été figé avant le coup d'envoi (sinon la comparaison porterait sur un
        # prono recalculé après le résultat — sans valeur). Aligné MPP.
        verdict = None
        if completed and preserved_predicted_score is not None:
            verdict = common.classify_prono(
                frozen_home, frozen_away, m.get("actual_home"), m.get("actual_away")
            )
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

        # Sans points MPP réels, on garde ces notes (le détail structuré
        # « Prono Mon Petit Prono » + « Option à variance » ne s'affiche que
        # quand les points sont chargés). Avec les points, ces lignes feraient
        # doublon — et leur registre « pari risqué / X2 » serait redondant.
        if not mpp_points and rec["differs"]:
            notes.append(
                f"Prono optimisé Mon Petit Prono : {live_predicted_score} maximise les points "
                f"attendus (bonus score exact +{rec['bonus']} {rec['tier']})."
            )

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
            "p_home": round(cal["home"] * 100),
            "p_draw": round(cal["draw"] * 100),
            "p_away": round(cal["away"] * 100),
            "probs": dict(cal),
            # Nutri-prono = le prono MPP : la pastille note la CONFIANCE que le
            # pick MPP tombe (proba de SON issue), pas la confiance du favori
            # modèle. Un pick contrarian (nul/outsider) tombe donc logiquement en
            # bas de l'échelle — c'est honnête (faible proba, gros lot). Proba
            # calibrée (cohérente avec le bandeau) ; en KO, la proba 120' de rec
            # n'a pas d'équivalent calibré → on garde le brut.
            "nutri": _confidence_nutriscore(
                rec["p_outcome"] if knockout else cal[rec["outcome"]], est),
            "mpp_outcome": rec["outcome"],
            "mpp_pick_pct": round((rec["p_outcome"] if knockout else cal[rec["outcome"]]) * 100),
            "mpp_base_points": (round(rec["base_points"]) if rec["base_points"] is not None else None),
            "mpp_upside": ({
                "score": f"{upside['score'][0]}-{upside['score'][1]}",
                "label": {"home": f"Victoire {home_label}", "draw": "Match nul",
                          "away": f"Victoire {away_label}"}[upside["outcome"]],
                "base_points": round(upside["base_points"]),
                "p_outcome": round(upside["p_outcome"] * 100),
            } if upside and upside["outcome"] != rec["outcome"] else None),
            "completed": completed,
            "verdict": verdict,
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


_TAB_LABELS = {"matchs": "Matchs", "paris": "Paris", "diagnostics": "Diagnostics"}

_CSS = "".join([
    ":root{--bg:#f6f4ec;--surface:#fffefa;--surface-2:#f2eee3;--surface-3:#fbfdff;"
    "--text:#1f2430;--muted:#5d6679;--line:#d8deea;--line-2:#b8c2d9;--track:#e7ebf3;"
    "--brand:#0f5c78;--brand-dark:#0a4a66;--brand-ink:#f4fbff;--brand-soft:#eaf2f8;"
    "--on-accent:#ffffff;"  # texte sur un fond sémantique saturé (ok/alert/nutri)
    "--ok:#257942;--ok-bg:#edf8f1;--ok-line:#9ad0af;"
    "--warn:#e8590c;--warn-text:#7c4b10;--warn-bg:#fff6e7;--warn-line:#f1cd8b;"
    "--alert:#8f2736;--alert-bg:#fdecec;--alert-line:#e4a7b1;"
    "--neutral:#64748b;--slate:#44536e;--away:#b45309;"
    "--nutri-a:#36b14f;--nutri-b:#8cc152;--nutri-c:#f0c000;--nutri-d:#ea8c2e;--nutri-e:#c0392b;--nutri-ink:#1c1407;"
    # Récap justesse : rampe de valeur dérivée de l'accent (teal plein → teal
    # désaturé → gris froid), distinguable en niveaux de gris. Volontairement
    # HORS ok/warn/alert (signaux) et hors gamme A–E (verdicts de pari) : une
    # erreur de prono n'est pas une faute morale du modèle.
    "--recap-exact:#0f5c78;--recap-bon:#5f97ab;--recap-erreur:#aab4c6;"
    # Page Paris (argent réel) : P&L coloré (gain vert / perte rouge, propres au
    # P&L, voisins des signaux) + podium métallique des 3 plus gros gains (or /
    # argent / cuivre, pâle et mat). Lisibilité « outil perso » assumée (cf. DA).
    "--pnl-gain:#1d7a40;--pnl-loss:#b02a37;"
    "--bet-gold:#735914;--bet-gold-bg:#f4e9c4;--bet-silver:#595f6b;"
    "--bet-silver-bg:#e8ebf0;--bet-copper:#85492c;--bet-copper-bg:#f1ddd1;"
    # Châssis dashboard (sidebar) : sombre CHAUD dérivé de l'encre, le sombre
    # s'arrête à la nav (jamais sur la donnée). Actif = teal lumineux (le teal
    # canvas est illisible sur sombre). Contrastes vérifiés AA au build.
    "--nav-bg:#1d2330;--nav-bg-2:#2a3344;--nav-line:#333d50;"
    "--nav-text:#c2cbdb;--nav-text-strong:#f4f7fb;"
    "--nav-active-bg:#143b4b;--nav-active-text:#86d4ec;"
    "--font-mono:ui-monospace,'SF Mono','Cascadia Mono',Menlo,Consolas,monospace;"
    "--shadow-floating:0 4px 16px rgb(0 0 0 / 0.10)}",
    "*{box-sizing:border-box}",
    "body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,'Apple Color Emoji','Segoe UI Emoji',sans-serif;margin:0;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;font-variant-numeric:tabular-nums}",
    # Dashboard : châssis sombre (sidebar) + canvas clair (contenu).
    ".app{display:grid;grid-template-columns:224px 1fr;min-height:100vh}",
    ".sidebar{background:var(--nav-bg);color:var(--nav-text);position:sticky;top:0;align-self:start;height:100vh;display:flex;flex-direction:column;padding:18px 14px;border-right:1px solid var(--nav-line)}",
    ".brand{display:flex;flex-direction:column;gap:2px;padding:4px 8px 0}",
    ".brand-name{font-family:var(--font-mono);font-weight:700;font-size:1.1rem;letter-spacing:.16em;color:var(--nav-text-strong)}",
    ".brand-sub{font-size:.72rem;color:var(--nav-text);opacity:.7}",
    ".side-nav{list-style:none;margin:20px 0 0;padding:0;display:flex;flex-direction:column;gap:3px}",
    ".nav-item{display:block;padding:9px 12px;border-radius:8px;color:var(--nav-text);text-decoration:none;font-weight:600;font-size:.92rem}",
    ".nav-item:hover{background:var(--nav-bg-2);color:var(--nav-text-strong)}",
    ".nav-item.active{background:var(--nav-active-bg);color:var(--nav-active-text)}",
    ".sidebar a:focus-visible{outline:3px solid color-mix(in srgb,var(--nav-active-text) 60%,transparent);outline-offset:2px}",
    ".sidebar-foot{margin-top:auto;display:flex;flex-direction:column;gap:6px;font-size:.76rem}",
    ".nav-health{display:flex;align-items:center;gap:7px;padding:8px 10px;border:1px solid var(--nav-line);border-radius:8px;color:var(--nav-text)}",
    ".nav-dot{width:8px;height:8px;border-radius:50%;flex:none}",
    ".nav-stat{color:var(--nav-text);opacity:.75;padding:0 4px;font-family:var(--font-mono)}",
    ".nav-mod{color:var(--nav-active-text);opacity:1}",
    ".canvas{padding:22px 28px 44px;max-width:1180px;min-width:0}",
    ".topbar{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:14px}",
    ".topbar h1{margin:0}",
    ".filter-wrap{display:flex;flex-direction:column;gap:4px;align-items:flex-end}",
    ".country-filter{width:240px;max-width:48vw;padding:9px 12px;border:1px solid var(--line-2);border-radius:10px;font-size:.95rem;background:var(--surface);color:var(--text)}",
    ".country-filter::placeholder{color:var(--muted)}",
    ".filter-count{font-family:var(--font-mono);font-size:.78rem;color:var(--muted);min-height:1em}",
    ".no-results{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;color:var(--muted);margin-bottom:14px}",
    ".link-btn{background:none;border:0;padding:0;color:var(--brand);font:inherit;font-weight:700;cursor:pointer;text-decoration:underline}",
    ".sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}",
    ".past-disclosure{margin:0 0 14px;border:1px solid var(--line);border-radius:14px;background:var(--surface)}",
    ".past-summary{display:flex;align-items:center;gap:10px;padding:13px 16px;cursor:pointer;font-weight:700;list-style:none}",
    ".past-summary::-webkit-details-marker{display:none}",
    ".past-summary::after{content:'\\25be';color:var(--muted);margin-left:14px;transition:transform .18s ease}",
    ".past-disclosure[open] .past-summary::after{transform:rotate(180deg)}",
    ".past-label{display:flex;align-items:center;gap:9px}",
    ".past-count{font-family:var(--font-mono);background:var(--surface-2);border:1px solid var(--line-2);border-radius:999px;padding:2px 9px;font-size:.82rem}",
    ".past-hint{font-weight:400;font-size:.76rem;color:var(--muted);margin-left:auto}",
    # La disclosure EST déjà la carte des passés : son corps est recessed
    # (ivoire) et les sections-jour à l'intérieur sont à plat (pas de carte ni
    # de coins arrondis imbriqués). Différenciation = le fond recessed, pas une
    # 2e bordure.
    ".past-body{padding:0 16px 12px;border-top:1px solid var(--line);background:var(--surface-2);border-radius:0 0 14px 14px}",
    ".past-body .day-section{background:transparent;border:0;border-radius:0;margin:0}",
    ".past-body .md-title{position:static;margin:0;padding:12px 0 8px;background:transparent;border-radius:0}",
    ".past-body .day-section+.day-section .md-title{border-top:1px solid var(--line);margin-top:6px}",
    # Survol du chart Justesse → petit tooltip listant les matchs (flottant,
    # sombre comme le châssis ; n'ouvre/ne déplace rien).
    ".recap-seg[data-tip],.recap-legend li[data-tip]{cursor:help}",
    ".recap-tip{position:fixed;z-index:60;max-width:340px;background:var(--nav-bg);color:var(--nav-text-strong);border:1px solid var(--nav-line);border-radius:8px;padding:7px 11px;font-size:.8rem;line-height:1.35;box-shadow:var(--shadow-floating);pointer-events:none}",
    "@media (prefers-reduced-motion:reduce){.past-summary::after{transition:none}}",
    "h1{margin:0;font-size:clamp(1.3rem,2vw,1.7rem);letter-spacing:.2px;line-height:1.1}",
    ".subtitle{margin:5px 0 0;color:var(--muted);font-size:.9rem;max-width:70ch}",
    ".panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 14px 12px;margin-bottom:14px}",
    # Galerie de paris : titre + grille de cards posés directement sur le canvas
    # (pas de panel autour — une seule épaisseur de bordure, cf. DA « élévation
    # plate »). Les cards SONT la surface, pas une boîte dans une boîte.
    ".bet-section{margin-bottom:18px}",
    ".bet-section>h3{margin:0 2px 2px}",
    ".bet-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px;margin-top:10px}",
    ".bet-card{border:1px solid var(--line);border-radius:12px;padding:12px 14px;background:var(--surface-3)}",
    ".bet-sel-line{font-size:1.02rem;font-weight:700;line-height:1.3}",
    ".bet-odds{font-family:var(--font-mono);color:var(--brand-dark);white-space:nowrap}",
    ".bet-context{font-size:.8rem;color:var(--muted);margin-top:3px;line-height:1.35}",
    ".bet-stake-line{display:flex;align-items:center;gap:9px;margin-top:9px;flex-wrap:wrap}",
    ".bet-stake{display:inline-block;padding:6px 11px;border-radius:6px;background:var(--surface-2);color:var(--text);border:1px solid var(--line-2);font-weight:700;font-size:.92rem;font-family:var(--font-mono)}",
    ".bet-return{font-size:.8rem;color:var(--muted)}",
    ".bet-why{margin-top:7px}",
    ".bet-why summary{font-size:.78rem;padding:3px 2px}",
    # Suivi des paris (argent réel) : bilan P&L/ROI + ledger. Distinct du récap
    # justesse (segmented bar) : ici une grille de métriques + une table, des
    # chips de statut (hors ok/warn/alert et hors gamme Nutri), un P&L coloré
    # (gain vert / perte rouge) et le podium métallique des 3 plus gros gains.
    ".suivi-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap}",
    ".suivi-head h2{margin:0;font-size:1rem;font-weight:700}",
    ".suivi-sample{font-family:var(--font-mono);font-size:.82rem;color:var(--muted)}",
    ".suivi-counts{margin:10px 0 0;font-size:.84rem;color:var(--slate)}",
    # Exposition « en cours » : bande pointillée (même langage que les chips de
    # statut en cours), fond transparent — c'est de l'argent non encore joué,
    # pas un résultat. Chiffres mono neutres (jamais vert : rien n'est gagné).
    ".encours{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;padding:9px 12px;border:1px dashed var(--line-2);border-radius:10px}",
    ".encours-tag{font-family:var(--font-mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);font-weight:700}",
    ".encours-figs{display:flex;gap:24px;flex-wrap:wrap;margin-left:auto}",
    ".encours-fig{display:flex;flex-direction:column;gap:2px}",
    ".encours-key{font-size:.66rem;text-transform:uppercase;letter-spacing:.07em;color:var(--muted)}",
    ".encours-val{font-family:var(--font-mono);font-weight:700;font-size:1.02rem;color:var(--text);line-height:1.1}",
    ".pnl-grid{display:flex;flex-wrap:wrap;gap:10px;margin-top:12px}",
    # Tuiles KPI : fond plein, SANS bordure — elles vivent déjà dans le panel
    # Suivi, pas de boîte-dans-boîte (cf. DA). La hiérarchie P&L > ROI/Mise vient
    # de la taille de la valeur (.pnl-val vs .sub) ; le signe du P&L se colore
    # gain vert / perte rouge (la valeur de Mise totale reste neutre).
    ".pnl-cell{flex:1 1 130px;border-radius:10px;padding:10px 12px;background:var(--surface-2)}",
    ".pnl-cell.lead{flex-basis:165px}",
    ".pnl-key{font-size:.68rem;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}",
    ".pnl-val{font-family:var(--font-mono);font-size:1.18rem;font-weight:700;margin-top:4px;color:var(--text);line-height:1.15}",
    ".pnl-val.sub{font-size:1rem;font-weight:600}",
    ".pnl-sample{font-size:.65rem;color:var(--muted);margin-top:3px;letter-spacing:.01em}",
    ".bets-table{margin-top:14px}",
    ".bets-table td{font-size:.92rem}",
    ".bets-table tbody tr:hover{background:color-mix(in srgb,var(--brand) 3%,var(--surface))}",
    ".bets-table .b-pari{line-height:1.3}",
    ".bets-table .b-sel{display:block;font-size:.78rem;color:var(--muted);margin-top:2px}",
    ".bets-table .b-num{font-family:var(--font-mono);text-align:right;white-space:nowrap}",
    # Cote vs mise : deux chiffres mono qu'on doit distinguer d'un coup d'œil
    # (lisibilité = priorité #1). La COTE est la donnée de décision → teal +
    # gras (le teal « signale la donnée », cohérent avec .bet-odds des cards) ;
    # la MISE est le montant engagé → encre neutre. Les deux restent tabulaires.
    ".bets-table .b-cote{color:var(--brand-dark);font-weight:700}",
    ".bets-table .b-mise{color:var(--text)}",
    ".bets-table th.col-num{text-align:right}",
    ".combo-tag{display:inline-block;margin-left:6px;padding:1px 7px;border-radius:999px;background:var(--surface-2);border:1px solid var(--line-2);font-size:.66rem;font-family:var(--font-mono);color:var(--slate);vertical-align:middle}",
    ".bet-placed{display:inline-block;margin-left:8px;padding:1px 8px;border-radius:999px;background:var(--surface-2);color:var(--slate);border:1px solid var(--line-2);font-size:.66rem;font-weight:700;vertical-align:middle;white-space:nowrap}",
    ".bet-card.is-placed{border-color:var(--line-2);background:var(--surface-2)}",
    ".bet-status{display:inline-flex;align-items:center;gap:6px;padding:3px 10px;border-radius:999px;font-size:.78rem;font-weight:700;border:1px solid var(--line-2);white-space:nowrap}",
    # Pastille seulement sur « Gagné » : micro-signal teal (la couleur donnée du
    # projet). Sur les statuts neutres, label + contour suffisent — pas
    # d'ornement redondant (le texte porte déjà le sens).
    ".bet-status-gagne::before{content:'';width:7px;height:7px;border-radius:50%;background:currentColor;flex:none;opacity:.85}",
    ".bet-status-gagne{background:var(--brand-soft);color:var(--brand-dark);border-color:color-mix(in srgb,var(--brand) 30%,var(--line-2))}",
    ".bet-status-perdu{background:var(--surface-2);color:var(--slate)}",
    ".bet-status-rembourse{background:var(--surface-2);color:var(--muted);border-style:dashed}",
    ".bet-status-encours{background:transparent;color:var(--muted);border-style:dashed}",
    ".b-net{font-family:var(--font-mono);font-weight:700;text-align:right;white-space:nowrap;color:var(--text)}",
    ".b-net-pending{color:var(--muted);font-weight:400}",
    # P&L coloré : gain vert / perte rouge (le signe +/− double l'info, jamais
    # la couleur seule). Sur le net cumulé/ROI et sur le net de chaque ligne.
    ".b-net.is-gain,.pnl-val.is-gain{color:var(--pnl-gain)}",
    ".b-net.is-loss,.pnl-val.is-loss{color:var(--pnl-loss)}",
    # Podium des 3 plus gros gains : médaillon métallique mat (pâle), rang en
    # mono. Le sens ne tient pas qu'à la couleur — rang chiffré + aria-label.
    ".medal{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;font-family:var(--font-mono);font-weight:700;font-size:.7rem;line-height:1;vertical-align:top;border:1px solid}",
    ".medal-1{background:var(--bet-gold-bg);color:var(--bet-gold);border-color:color-mix(in srgb,var(--bet-gold) 35%,var(--line-2))}",
    ".medal-2{background:var(--bet-silver-bg);color:var(--bet-silver);border-color:color-mix(in srgb,var(--bet-silver) 35%,var(--line-2))}",
    ".medal-3{background:var(--bet-copper-bg);color:var(--bet-copper);border-color:color-mix(in srgb,var(--bet-copper) 35%,var(--line-2))}",
    # Le médaillon vit dans une gouttière de largeur FIXE présente sur TOUTES les
    # lignes (vide hors podium) → les libellés gardent le même bord gauche, et le
    # texte wrappé (combinés longs) s'aligne sous lui-même, pas sous le médaillon.
    ".b-pari .pari-main{display:flex;align-items:flex-start;gap:7px}",
    ".medal-slot{flex:none;width:18px;text-align:center}",
    ".pari-text{flex:1;min-width:0}",
    ".suivi-note{margin:11px 0 0;font-size:.78rem;color:var(--muted);max-width:75ch;line-height:1.35}",
    # Mobile (hors cible, mais on évite le rendu cassé) : table en lignes
    # étiquetées plutôt que la dégradation générique sans en-têtes.
    "@media (max-width:760px){.bets-table td{display:flex;justify-content:space-between;gap:12px;text-align:right}"
    ".bets-table td::before{content:attr(data-label);color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.07em;text-align:left;font-weight:700}"
    ".bets-table .b-sel{text-align:right}}",
    "a:focus-visible,summary:focus-visible,input:focus-visible,button:focus-visible{outline:3px solid color-mix(in srgb,var(--brand) 45%,white);outline-offset:2px;border-radius:6px}",
    ".stats{display:flex;gap:8px;flex-wrap:wrap}",
    ".stamp{background:var(--surface-2);border:1px solid var(--line);border-radius:999px;padding:6px 10px;font-size:.78rem;color:var(--muted)}",
    "table{width:100%;border-collapse:collapse;table-layout:fixed}",
    "th,td{padding:9px 8px;vertical-align:middle}",
    "thead th{text-align:left;font-size:.7rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em;padding-bottom:4px}",
    "tbody tr{border-top:1px solid var(--line)}",
    "tbody tr.match-row:hover{background:color-mix(in srgb,var(--brand) 3%,var(--surface))}",
    "td strong{font-weight:700}",
    ".nutri{display:inline-block;min-width:30px;text-align:center;padding:6px 0;border-radius:8px;font-weight:700;font-size:.88rem;color:var(--nutri-ink)}",
    ".nutri-a{background:var(--nutri-a)}",
    ".nutri-b{background:var(--nutri-b)}",
    ".nutri-c{background:var(--nutri-c)}",
    ".nutri-d{background:var(--nutri-d)}",
    ".nutri-e{background:var(--nutri-e);color:var(--on-accent)}",
    # Sticky en tête de panneau ; top:0 = le canvas scrolle sous le bord haut
    # (plus de tabbar à compenser depuis la refonte dashboard).
    ".md-title{display:flex;justify-content:space-between;gap:8px;align-items:baseline;position:sticky;top:0;z-index:5;background:var(--surface);margin:-14px -14px 4px;padding:12px 14px 8px;border-bottom:1px solid var(--line);border-radius:14px 14px 0 0}",
    ".md-title h2{margin:0;font-size:1rem;font-weight:700}",
    ".day-mod{color:var(--warn-text);font-weight:700}",
    ".cell-meta .kick{display:block;font-family:var(--font-mono);font-weight:700;font-size:.95rem;line-height:1.2}",
    ".cell-meta .kick-tbd{color:var(--muted);font-weight:400}",
    ".meta-sub{display:block;font-size:.72rem;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}",
    ".cell-teams{font-size:.98rem;line-height:1.35}",
    ".team-name{display:inline}",
    ".team-sep{color:var(--muted);margin:0 7px}",
    ".score-chip{display:inline-flex;align-items:center;justify-content:center;min-width:64px;padding:6px 10px;border-radius:999px;background:var(--surface-2);color:var(--text);border:1px solid var(--line-2);font-weight:700;font-size:.95rem;line-height:1;font-family:var(--font-mono)}",
    # Recentrage confiance/risque : le verdict mène la colonne « Pronostic », le
    # score sec passe en sous-ligne discrète. Chips SOBRES (pas de rouge promo,
    # cf. DA) : solide = teal calme (la donnée), serré = neutre, piège/ouvert =
    # signal de prudence (warn ambré sobre / neutre pointillé), jamais d'urgence.
    # Bandeau récap confiance : combien de favoris solides (rien à décider) vs à
    # examiner — pour aller droit aux matchs où l'analyse sert. Sobre, scannable.
    ".conf-summary{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 14px;padding:10px 14px;background:var(--surface);border:1px solid var(--line);border-radius:12px}",
    ".cs-chip{font-weight:700;font-size:.84rem;padding:4px 11px;border-radius:999px;white-space:nowrap}",
    ".cs-solide{background:var(--surface-2);color:var(--text);border:1px solid var(--line-2)}",
    ".cs-watch{background:var(--warn-bg);color:var(--warn-text);border:1px solid var(--warn-line)}",
    ".cs-note{font-size:.8rem;color:var(--muted)}",
    ".verdict-line{display:block}",
    # La COULEUR ne signale que le RISQUE : piège/ouvert en ambré (à examiner),
    # solide/serré neutres — pour ne pas faire doublon avec le badge Nutri (la
    # note de confiance signature, cf. DA). Le verdict mène la colonne (0.9rem/700)
    # nettement au-dessus du score démoté (0.75rem).
    ".conf-verdict{display:inline-block;padding:4px 10px;border-radius:999px;font-weight:700;font-size:.9rem;line-height:1.15;border:1px solid var(--line-2);background:var(--surface-2);color:var(--text)}",
    ".cv-solide{background:var(--surface-2);color:var(--text);border-color:var(--line-2)}",
    ".cv-serre{background:var(--surface-2);color:var(--muted);border-color:var(--line-2)}",
    ".cv-piege{background:var(--warn-bg);color:var(--warn-text);border-color:var(--warn-line)}",
    ".cv-ouvert{background:var(--warn-bg);color:var(--warn-text);border-color:var(--warn-line);border-style:dashed}",
    # Picks contrarian (le pick EV ne suit pas le favori) : même ambré « non
    # trivial, regarde » — verdict + score nul + Nutri E racontent une histoire.
    ".cv-nul{background:var(--warn-bg);color:var(--warn-text);border-color:var(--warn-line)}",
    ".cv-valeur{background:var(--warn-bg);color:var(--warn-text);border-color:var(--warn-line)}",
    ".score-sub-line{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin-top:5px}",
    ".score-sub-line .delta{margin-top:0}",
    ".score-sub{font-family:var(--font-mono);font-size:.75rem;color:var(--muted);white-space:nowrap}",
    ".delta{display:flex;width:max-content;align-items:center;gap:6px;margin-top:5px;padding:3px 8px;border-radius:6px;background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--warn-text);font-size:.76rem;font-weight:700;white-space:nowrap}",
    ".delta::before{content:'';width:7px;height:7px;border-radius:50%;background:var(--warn);flex:none}",
    ".delta .delta-scores{font-family:var(--font-mono)}",
    "@media (prefers-reduced-motion:reduce){.tab{transition:none}}",
    ".score-dual{display:inline-flex;align-items:center;gap:6px;flex-wrap:wrap}",
    ".score-chip-real{background:var(--ok);color:var(--on-accent);border-color:transparent;font-size:.86rem;min-width:88px}",
    ".score-chip-prono{font-size:.86rem;min-width:98px}",
    # Verdict par match (table des passés) : même rampe que le récap justesse.
    # Pleine couleur pour exact/bon, atténué pour erreur — neutre, descriptif.
    ".cell-verdict{white-space:nowrap}",
    ".verdict-chip{display:inline-flex;align-items:center;justify-content:center;padding:5px 11px;border-radius:999px;font-weight:700;font-size:.82rem;line-height:1}",
    ".verdict-exact{background:var(--recap-exact);color:#fff}",
    ".verdict-bon{background:var(--recap-bon);color:#fff}",
    ".verdict-erreur{background:var(--recap-erreur);color:var(--text)}",
    ".verdict-na{background:var(--surface-2);color:var(--muted);border:1px solid var(--line-2)}",
    # Récap justesse (tête de l'onglet Passés) — barre segmentée 100 %, pas de donut.
    ".recap-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:10px}",
    ".recap-head h2{margin:0;font-size:1rem;font-weight:700}",
    ".recap-sample{font-family:var(--font-mono);font-size:.82rem;color:var(--muted)}",
    ".recap-bar{display:flex;height:14px;border-radius:999px;overflow:hidden;background:var(--track)}",
    ".recap-seg{display:block;height:100%}",
    ".recap-seg+.recap-seg{border-left:3px solid var(--surface)}",
    ".recap-seg-exact{background:var(--recap-exact)}",
    ".recap-seg-bon{background:var(--recap-bon)}",
    ".recap-seg-erreur{background:var(--recap-erreur)}",
    ".recap-small .recap-bar{opacity:.7}",
    ".recap-legend{list-style:none;display:flex;flex-wrap:wrap;gap:6px 18px;margin:10px 0 0;padding:0;font-size:.86rem}",
    ".recap-legend li{display:flex;align-items:center;gap:7px}",
    ".recap-legend strong{font-family:var(--font-mono);font-weight:700;color:var(--text)}",
    ".swatch{width:11px;height:11px;border-radius:3px;flex:none;border:1px solid var(--line-2)}",
    ".swatch-exact{background:var(--recap-exact)}",
    ".swatch-bon{background:var(--recap-bon)}",
    ".swatch-erreur{background:var(--recap-erreur)}",
    ".recap-caveat{margin:9px 0 0;font-size:.82rem;color:var(--slate);font-weight:700}",
    ".recap-note{margin:9px 0 0;font-size:.78rem;color:var(--muted);max-width:75ch;line-height:1.35}",
    ".recap code{font-family:var(--font-mono);font-size:.92em}",
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
    "details{border:0;background:transparent}",
    "summary{cursor:pointer;font-size:.84rem;color:var(--brand);font-weight:700;display:inline-block;padding:6px 4px;border-radius:6px}",
    "summary:hover{text-decoration:underline}",
    "summary::marker{color:var(--brand)}",
    ".note-list{margin:8px 0 0;padding:8px 10px 8px 24px;color:var(--muted);font-size:.8rem;line-height:1.3;background:var(--surface-3);border:1px solid var(--line);border-radius:10px;max-width:75ch}",
    ".details-btn{background:none;border:0;cursor:pointer;font:inherit;font-size:.84rem;color:var(--brand);font-weight:700;padding:6px 4px;border-radius:6px}",
    ".details-btn:hover{text-decoration:underline}",
    "tr.note-row{border-top:0}",
    "tr.note-row>td{padding:0 8px 10px}",
    "tr.note-row .note-list{margin:0}",
    ".muted{color:var(--muted);font-size:.9rem}",
    ".err{background:var(--alert);color:var(--on-accent);padding:11px 12px;border-radius:10px;margin-bottom:10px}",
    ".err a{color:var(--on-accent);font-weight:700}",
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
    ".bankroll-form{display:flex;align-items:flex-end;gap:8px;margin-top:10px;flex-wrap:wrap}",
    ".bankroll-form .field{display:flex;flex-direction:column;gap:4px}",
    ".bankroll-form label{font-size:.78rem;font-weight:700;color:var(--muted)}",
    ".bankroll-form input{width:120px;padding:9px 10px;border:1px solid var(--line-2);border-radius:8px;font-size:.95rem;background:var(--surface);color:var(--text)}",
    ".bankroll-form button{padding:10px 14px;border:0;border-radius:8px;background:var(--brand);color:var(--brand-ink);font-weight:700;font-size:.85rem;cursor:pointer}",
    ".bankroll-form button:hover{background:var(--brand-dark)}",
    "@media (max-width:860px){.info-grid{grid-template-columns:1fr}}",
    "@media (max-width:760px){.app{grid-template-columns:1fr}.sidebar{position:static;height:auto;flex-direction:row;align-items:center;gap:12px;flex-wrap:wrap}.side-nav{flex-direction:row;margin:0}.sidebar-foot{display:none}.canvas{padding:14px 10px 20px}.panel{padding:11px 10px}"
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
    ".cell-details{display:inline-block;vertical-align:middle;margin-top:8px}"
    "tr.note-row{border-top:0;padding:0}tr.note-row>td{padding:0 0 8px}"
    "summary{padding:10px 4px}}",
    "@media (max-width:480px){.prob-bar{display:none}}",
])


def _render_sidebar(safe_tab: str, health: Optional[Dict], health_meta: Dict[str, str],
                    n_future: int, n_past: int, n_changed: int = 0) -> List[str]:
    """Châssis du dashboard : marque + nav 3 entrées + statut data en pied.

    Nav server-rendered (3 `<a href>` réels) : marche sans JS, actif calculé
    serveur (fond teinté + encre + aria-current = trois signaux redondants)."""
    def item(key: str, label: str) -> str:
        active = " active" if safe_tab == key else ""
        current = " aria-current='page'" if safe_tab == key else ""
        return (f"<li><a href='/?tab={key}' class='nav-item{active}'{current}>"
                f"{html.escape(label)}</a></li>")

    parts = [
        "<aside class='sidebar'>",
        "<div class='brand'><span class='brand-name'>PRONO</span>"
        "<span class='brand-sub'>Coupe du Monde 2026</span></div>",
        "<nav aria-label='Navigation principale'><ul class='side-nav'>",
        item("matchs", "Matchs"),
        item("paris", "Paris"),
        item("diagnostics", "Diagnostics"),
        "</ul></nav>",
        "<div class='sidebar-foot'>",
    ]
    if health and (health or {}).get("level") != "good":
        # Feu data = un signal qualité : couleur sémantique légitime (ok/warn/alert).
        dot = "var(--alert)" if "critical" in health_meta["class"] else "var(--warn)"
        parts.append(
            f"<div class='nav-health'><span class='nav-dot' style='background:{dot}'></span>"
            f"Feu data : {html.escape(health_meta['label'])}</div>"
        )
    parts.append(f"<div class='nav-stat'>{n_future} à venir · {n_past} joués</div>")
    if n_changed:
        plural = "s" if n_changed > 1 else ""
        parts.append(f"<div class='nav-stat nav-mod'>{n_changed} prono{plural} modifié{plural}</div>")
    parts.extend(["</div>", "</aside>"])
    return parts


def _render_day_sections(grouped, past: bool = False) -> List[str]:
    """Sections par jour (panneau + table) pour les matchs à venir.

    Les passés ont leur propre rendu compact (:func:`_render_past_table`) sans
    regroupement par date ; ce découpage par jour ne sert plus que les futurs."""
    thead = ("<th style='width:11%'>Heure (FR)</th><th style='width:31%'>Match</th>"
             "<th style='width:18%'>Pronostic</th><th style='width:7%'>Conf.</th>"
             "<th style='width:20%'>Probabilités 1 · N · 2</th>"
             "<th style='width:13%'>Détails</th>")
    out: List[str] = []
    for day, md_rows in grouped:
        day_label = _fr_date_label(day)
        n_mod_day = sum(1 for r in md_rows if r.get("prediction_changed"))
        mod_html = ""
        if n_mod_day:
            plural = "s" if n_mod_day > 1 else ""
            mod_html = f" · <span class='day-mod'>{n_mod_day} modifié{plural}</span>"
        day_count = f"<span class='tiny'>{len(md_rows)} match{'s' if len(md_rows) > 1 else ''}{mod_html}</span>"
        out.extend([
            "<section class='panel day-section'>",
            "<div class='md-title'>",
            f"<h2>{html.escape(day_label)}</h2>",
            day_count,
            "</div>",
            "<table><thead><tr>",
            thead,
            "</tr></thead><tbody>",
        ])
        for r in md_rows:
            out.extend(_render_row(r, past=past))
        out.extend(["</tbody></table>", "</section>"])
    return out


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


def _placed_picks(bets: Optional[List[Dict]]) -> Dict[str, set]:
    """Ce que Baptiste a réellement joué sur Winamax (data/bets.json), pour
    marquer dans les paris PROPOSÉS ceux déjà pris — il voit le reste à faire.

    On distingue un **simple** joué (une sélection) d'un **combiné** joué (un
    ensemble de sélections) : un combiné proposé n'est « déjà joué » que si ce
    combiné-là a été pris — **pas** si ses jambes ont été jouées séparément en
    simples (jouer Iran *et* Mexique en simples ≠ avoir joué le combiné
    Iran+Mexique). Renvoie ``{"singles": {(match_id, issue)},
    "combos": {frozenset({(match_id, issue), …})}}``, croisé par id de fixture
    (robuste aux libellés FR/EN). Les paris sans ``legs`` ne matchent rien."""
    singles: set = set()
    combos: set = set()
    for b in (bets or []):
        picks = {(str(leg.get("match")).upper(), leg.get("pick"))
                 for leg in b.get("legs", [])
                 if leg.get("match") and leg.get("pick")}
        if not picks:
            continue
        if b.get("combo") or len(picks) > 1:
            combos.add(frozenset(picks))
        else:
            singles |= picks
    return {"singles": singles, "combos": combos}


_PLACED_BADGE = "<span class='bet-placed' title='Tu as déjà joué cette sélection sur Winamax'>déjà joué</span>"


def _render_paris(rec: Optional[Dict], bankroll: float, bet_blocked: bool,
                  placed_picks: Optional[Dict[str, set]] = None) -> List[str]:
    placed = placed_picks or {"singles": set(), "combos": set()}
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
        "<section class='bet-section'>",
        "<h3>Paris simples (value uniquement)</h3>",
        "<div class='bet-grid'>",
    ])
    if rec["singles"]:
        for s in rec["singles"]:
            b = s["bet"]
            sel = _sel_fr(b["sel"], s["home"], s["away"])
            ret = s["stake"] * b["odds"]
            placed_tag = (_PLACED_BADGE
                          if (str(s.get("match_id", "")).upper(), b["sel"]) in placed["singles"] else "")
            # Ordre du ticket Winamax : sélection + cote, contexte, mise, retour
            # — la recopie se fait position à position, le calcul passe en détail.
            parts.extend([
                f"<article class='bet-card{' is-placed' if placed_tag else ''}'>",
                f"<div class='bet-sel-line'>{html.escape(sel)} <span class='bet-odds'>@ {b['odds']:.2f}</span>{placed_tag}</div>",
                "<div class='bet-context'>1N2</div>",
                f"<div class='bet-context'>{html.escape(s['label'])}"
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
        "<section class='bet-section'>",
        "<h3>Combinés (2 sélections max &middot; mise minime)</h3>",
        "<div class='bet-grid'>",
    ])
    if rec["combos"]:
        for c in rec["combos"]:
            ret = c["stake"] * c["combined_odds"]
            # « déjà joué » porte sur le combiné ENTIER : un seul badge, en tête
            # de la card, et seulement si ce combiné-là (même jeu de jambes) a
            # été pris — pas si ses jambes l'ont été séparément en simples.
            legs_key = frozenset((str(leg.get("match_id", "")).upper(), leg["sel"])
                                 for leg in c["legs"])
            placed_tag = _PLACED_BADGE if legs_key in placed["combos"] else ""
            parts.append(f"<article class='bet-card{' is-placed' if placed_tag else ''}'>")
            parts.append(
                f"<div class='bet-sel-line'>Combiné {len(c['legs'])} sélections "
                f"<span class='bet-odds'>@ {c['combined_odds']:.2f}</span>{placed_tag}</div>"
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


# Libellés FR des statuts de règlement + classe du chip (neutre, double encodé :
# le texte porte le sens, la couleur ne fait que renforcer).
_BET_STATUS_UI = {
    "gagne": ("Gagné", "bet-status-gagne"),
    "perdu": ("Perdu", "bet-status-perdu"),
    "rembourse": ("Remboursé", "bet-status-rembourse"),
    "en_cours": ("En cours", "bet-status-encours"),
}


def _bet_label(b: Dict) -> str:
    return str(b.get("label") or b.get("match") or "Pari").strip() or "Pari"


def _net_txt(value: float) -> str:
    """Gain net formaté : signe seulement s'il est non nul (évite « +0,00 € »)."""
    return "0,00 €" if abs(value) < 0.005 else _eur_signed(value)


def _net_class(value: Optional[float]) -> str:
    """Classe couleur du P&L : gain (vert) / perte (rouge) / neutre (0 ou en cours).

    Le signe ±  est déjà rendu dans le texte (_net_txt) : la couleur double
    l'info, elle ne la porte jamais seule (a11y).
    """
    if value is None or abs(value) < 0.005:
        return ""
    return "is-gain" if value > 0 else "is-loss"


def _medal_html(rank: int) -> str:
    """Médaillon podium (1/2/3) pour les 3 plus gros gains du tournoi.

    Le rang chiffré + l'aria-label portent le sens — pas seulement la couleur
    du métal (or/argent/cuivre).
    """
    lab = {1: "1er", 2: "2e", 3: "3e"}.get(rank, str(rank))
    return (f"<span class='medal medal-{rank}' "
            f"aria-label='{lab} plus gros gain du tournoi' "
            f"title='{lab} plus gros gain du tournoi'>{rank}</span>")


def _render_suivi_paris(bets: List[Dict]) -> List[str]:
    """Suivi des paris réels (terminés + en cours) + bilan cumulé tournoi.

    Bilan « argent réel » (mise engagée, P&L net, ROI), distinct du récap
    justesse des pronos (1N2). Lisibilité « outil perso » assumée (cf. DA) :
    gain en vert / perte en rouge sur le P&L, et un médaillon or/argent/cuivre
    sur les 3 plus gros gains du tournoi. Données écrites par la couche
    ask-Claude (data/bets.json), jamais saisies sur le site.
    """
    if not bets:
        return [
            "<section class='panel' aria-labelledby='suivi-title'>",
            "<div class='suivi-head'><h2 id='suivi-title'>Suivi des paris</h2></div>",
            "<p class='muted' style='margin:8px 0 0'>Aucun pari enregistré pour l'instant. "
            "Les paris et leur résultat (gagné / perdu / remboursé) s'ajoutent en les dictant à "
            "Claude, qui met à jour <code>data/bets.json</code> — aucune saisie sur le site.</p>",
            "</section>",
        ]

    agg = common.tally_bets(bets)
    n_set = agg["n_settled"]

    sample = f"{n_set} pari{'s' if n_set != 1 else ''} réglé{'s' if n_set != 1 else ''}"
    if agg["n_pending"]:
        sample += f" · {agg['n_pending']} en cours"

    out = [
        "<section class='panel' aria-labelledby='suivi-title'>",
        "<div class='suivi-head'>",
        "<h2 id='suivi-title'>Suivi des paris</h2>",
        f"<span class='suivi-sample'>{html.escape(sample)}</span>",
        "</div>",
    ]

    # Bilan cumulé : P&L net et ROI en tête (gain vert / perte rouge). Affiché
    # dès qu'un pari est réglé ; sinon une ligne d'attente (en cours = pas de P&L).
    if n_set:
        roi_txt = (f"{agg['roi'] * 100:+.1f} %".replace(".", ",")
                   if agg["roi"] is not None else "—")
        roi_sample = f"· {n_set} réglé{'s' if n_set != 1 else ''}"
        out.extend([
            "<div class='pnl-grid'>",
            "<div class='pnl-cell lead'><div class='pnl-key'>Gain net (P&amp;L)</div>"
            f"<div class='pnl-val {_net_class(agg['net'])}'>{html.escape(_net_txt(agg['net']))}</div></div>",
            "<div class='pnl-cell' title='ROI = gain net / mise totale engagée'>"
            "<div class='pnl-key'>ROI</div>"
            f"<div class='pnl-val sub {_net_class(agg['net'])}'>{html.escape(roi_txt)}</div>"
            f"<div class='pnl-sample'>{html.escape(roi_sample)}</div></div>",
            "<div class='pnl-cell'><div class='pnl-key'>Mise totale</div>"
            f"<div class='pnl-val sub'>{html.escape(_eur(agg['staked'], 2))}</div></div>",
            "</div>",
        ])
        # Compteurs gagnés/perdus/remboursés : ligne discrète sous la grille
        # (objet lexical, séparé des cellules chiffrées).
        counts = [f"{agg['n_won']} gagné{'s' if agg['n_won'] != 1 else ''}",
                  f"{agg['n_lost']} perdu{'s' if agg['n_lost'] != 1 else ''}"]
        if agg["n_refunded"]:
            counts.append(f"{agg['n_refunded']} remboursé{'s' if agg['n_refunded'] != 1 else ''}")
        out.append(f"<p class='suivi-counts'>{html.escape(' · '.join(counts))}</p>")
    else:
        out.append("<p class='muted' style='margin:8px 0 0'>Aucun pari réglé pour l'instant — "
                   "le bilan (P&amp;L, ROI) s'affiche dès le premier résultat.</p>")

    # Exposition des paris EN COURS : mise totale engagée + gain total possible
    # si tout passe. Distinct du bilan réglé (argent non encore joué) → traité en
    # bande à part, langage « en cours » (pointillés) plutôt qu'en tuile KPI.
    if agg["n_pending"]:
        np = agg["n_pending"]
        out.extend([
            "<div class='encours'>",
            f"<span class='encours-tag'>{np} en cours</span>",
            "<div class='encours-figs'>",
            "<div class='encours-fig'><span class='encours-key'>Mise totale en cours</span>"
            f"<span class='encours-val'>{html.escape(_eur(agg['staked_pending'], 2))}</span></div>",
            "<div class='encours-fig'><span class='encours-key'>Gain total possible</span>"
            f"<span class='encours-val'>{html.escape(_eur(agg['potential_pending'], 2))}</span></div>",
            "</div></div>",
        ])

    # Podium des 3 plus gros gains : médaillon or/argent/cuivre sur les lignes
    # au plus gros gain net (positif). Identité « ledger » de la page Paris,
    # outil perso (cf. DA). Clé = identité d'objet (robuste aux paris sans id).
    winners = [(n, b) for b in bets
               if (n := common.bet_net(b)) is not None and n > 0.005]
    winners.sort(key=lambda t: t[0], reverse=True)
    podium = {id(b): rank for rank, (_n, b) in enumerate(winners[:3], start=1)}

    # Ledger dans le MÊME panel : un seul bloc « Suivi des paris » (bilan +
    # historique), pas deux cards juxtaposées. Plus récents en tête.
    out.extend([
        "<table class='bets-table'>",
        "<colgroup><col style='width:40%'><col style='width:12%'><col style='width:13%'>"
        "<col style='width:19%'><col style='width:16%'></colgroup>",
        "<thead><tr><th>Pari</th><th class='col-num'>Cote</th><th class='col-num'>Mise</th>"
        "<th>Statut</th><th class='col-num'>Net</th></tr></thead>",
        "<tbody>",
    ])
    for b in reversed(bets):
        status = common.bet_status(b)
        status_label, status_cls = _BET_STATUS_UI[status]
        net = common.bet_net(b)
        try:
            odds_txt = f"{float(b.get('odds')):.2f}".replace(".", ",")
        except (TypeError, ValueError):
            odds_txt = "—"
        try:
            stake_txt = _eur(float(b.get("stake")), 2)
        except (TypeError, ValueError):
            stake_txt = "—"
        sel = str(b.get("sel") or "").strip()
        combo_tag = "<span class='combo-tag'>combiné</span>" if b.get("combo") else ""
        sel_html = f"<span class='b-sel'>{html.escape(sel)}</span>" if sel else ""
        medal_html = _medal_html(podium[id(b)]) if id(b) in podium else ""
        net_html = ("<span class='b-net-pending'>—</span>" if net is None
                    else html.escape(_net_txt(net)))
        out.extend([
            "<tr>",
            f"<td data-label='Pari' class='b-pari'><span class='pari-main'>"
            f"<span class='medal-slot'>{medal_html}</span>"
            f"<span class='pari-text'>{html.escape(_bet_label(b))}{combo_tag}{sel_html}</span></span></td>",
            f"<td data-label='Cote' class='b-num b-cote'>{odds_txt}</td>",
            f"<td data-label='Mise' class='b-num b-mise'>{html.escape(stake_txt)}</td>",
            f"<td data-label='Statut'><span class='bet-status {status_cls}'>{status_label}</span></td>",
            f"<td data-label='Net' class='b-net {_net_class(net)}'>{net_html}</td>",
            "</tr>",
        ])
    out.append("</tbody></table>")
    out.append(
        "<p class='suivi-note'>Bilan « argent réel » (mises Winamax), distinct du récap "
        "justesse des pronos (1N2).</p>"
    )
    out.append("</section>")
    return out


# Verdict de justesse par match (cf. common.classify_prono). On reprend la
# rampe de couleurs du récap (--recap-*) pour que la ligne et le chart parlent
# le même langage ; libellés au singulier. Neutre par construction (un « Manqué »
# s'affiche aussi sobrement qu'un « Exact ») — aucune note de certitude.
_VERDICT_META = {
    "exact": ("Exact", "exact"),
    "bon": ("Bon résultat", "bon"),
    "erreur": ("Manqué", "erreur"),
}


def _verdict_chip(verdict: Optional[str]) -> str:
    meta = _VERDICT_META.get(verdict)
    if meta is None:
        # Match joué mais aucun prono figé avant le coup d'envoi : rien à juger.
        return "<span class='verdict-chip verdict-na' title='Pas de prono figé avant match'>&mdash;</span>"
    label, cls = meta
    return (
        f"<span class='verdict-chip verdict-{cls}' "
        f"aria-label='Prono : {html.escape(label)}'>{html.escape(label)}</span>"
    )


def _render_past_table(past_rows: List[Dict]) -> List[str]:
    """Matchs passés en une seule table compacte, sans regroupement par date.

    La date, l'heure et les méta (J/Gr/id) sont volontairement absentes : une
    fois le match joué, l'info utile est Match · Réel/Prono · Verdict. L'ordre
    chronologique des lignes est conservé (past_rows arrive déjà trié)."""
    out: List[str] = [
        "<section class='panel day-section past-table'>",
        "<table><thead><tr>",
        "<th>Match</th><th style='width:32%'>Réel · Prono</th>"
        "<th style='width:16%'>Verdict</th>",
        "</tr></thead><tbody>",
    ]
    for r in past_rows:
        out.extend(_render_row(r, past=True))
    out.extend(["</tbody></table>", "</section>"])
    return out


def _render_row(r: Dict, past: bool = False) -> List[str]:
    home_label = r["home_label"]
    away_label = r["away_label"]
    # Chaîne pour le filtre pays côté client : noms anglais (clés ratings) ET
    # libellés FR, pour qu'on retrouve aussi bien « Korea » que « Corée ».
    search = html.escape(" ".join(
        str(x) for x in (r["home"], r["away"], home_label, away_label)
    ).lower())
    row_open = f"<tr class='match-row' data-search='{search}'>"

    kick = r.get("kickoff_paris") or ""
    kick_html = (f"<span class='kick'>{html.escape(kick)}</span>" if kick
                 else "<span class='kick kick-tbd'>&mdash;</span>")
    meta_sub = (f"J{html.escape(str(r['matchday']))} · Gr. {html.escape(str(r['group']))}"
                f" · {html.escape(str(r['id']))}")
    meta_cell = f"<td class='cell-meta'>{kick_html}<span class='meta-sub'>{meta_sub}</span></td>"
    teams_cell = (
        f"<td class='cell-teams'>"
        f"<span class='flag'>{r['home_flag']}</span> <span class='team-name'>{html.escape(home_label)}</span>"
        f"<span class='team-sep'>&ndash;</span>"
        f"<span class='team-name'>{html.escape(away_label)}</span> <span class='flag'>{r['away_flag']}</span>"
        f"</td>"
    )

    # Matchs passés : ligne réduite à l'essentiel — Match · Réel/Prono · Verdict.
    # On laisse tomber l'heure et les méta (J/Gr/id) : une fois le score connu,
    # seule compte la lecture réel vs prono et « ai-je eu bon ». La confiance et
    # les probas (prévisions d'avant-match) n'ont plus de valeur ici.
    if past:
        score_block = (
            f"<span class='score-dual'>"
            f"<span class='score-chip score-chip-real'>Réel {html.escape(r['actual_score'] or r['score'])}</span>"
            f"<span class='score-chip score-chip-prono'>Prono {html.escape(r['predicted_score'])}</span>"
            f"</span>"
        )
        return [
            row_open,
            teams_cell,
            f"<td class='cell-prono'>{score_block}</td>",
            f"<td class='cell-verdict'>{_verdict_chip(r.get('verdict'))}</td>",
            "</tr>",
        ]

    est = " *" if r["est"] else ""
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
        f"title='Confiance que le prono Mon Petit Prono tombe — {html.escape(r['nutri'])} (A = forte, E = faible)' "
        f"aria-label='Confiance que le prono tombe {html.escape(r['nutri'])} sur A à E'>{html.escape(r['nutri'])}</span>"
    )

    delta_badge = ""
    if r.get("prediction_changed"):
        delta_badge = (
            f"<span class='delta' "
            f"title='Prono recalculé après une mise à jour des données'>"
            f"Modifié <span class='delta-scores'>{html.escape(r['predicted_score'])} &rarr; "
            f"{html.escape(r['predicted_score_live'])}</span></span>"
        )
    # Recentrage confiance/risque : le VERDICT (sur quel favori miser / pas miser)
    # est la tête d'affiche de la colonne ; le score sec passe en sous-ligne — il
    # reste pour reporter dans MPP, mais il n'est plus présenté comme « la »
    # prédiction (le score du favori, Baptiste le sort de tête ; la valeur est
    # ailleurs). La distribution 1N2 reste l'objet premier (cf. DA).
    # Verdict de la décision JOUÉE (le pick MPP), pas le favori 1N2 : sur un pick
    # contrarian (nul/outsider) il dit « Jouer le nul » et non « Favori solide »,
    # pour qu'il s'accorde avec le score « prono 0-0 » et la pastille Nutri E.
    pick_verdict = _pick_verdict(ph, pd, pa, r.get("mpp_outcome", ""))
    verdict_block = (
        f"<span class='conf-verdict cv-{pick_verdict['tier']}' "
        f"title='{html.escape(pick_verdict['why'])}' "
        f"aria-label='{html.escape(pick_verdict['label'])} — {html.escape(pick_verdict['why'])}'>"
        f"{html.escape(pick_verdict['label'])}</span>"
    )
    score_sub = (
        f"<span class='score-sub' title='Prono à reporter dans MPP (maximise les points)' "
        f"aria-label='Prono {html.escape(r['score'])}'>prono {html.escape(r['score'])}</span>"
    )

    parts = [row_open, meta_cell, teams_cell]
    parts.append(
        f"<td class='cell-prono'><span class='verdict-line'>{verdict_block}</span>"
        f"<span class='score-sub-line'>{score_sub}{delta_badge}</span></td>"
    )
    parts.append(f"<td class='cell-nutri'>{nutri_chip}</td>")
    parts.append(f"<td class='cell-prob'>{prob_block}</td>")

    notes_id = f"notes-{html.escape(str(r['id']))}"
    parts.append(
        f"<td class='cell-details'><button type='button' class='details-btn' "
        f"aria-expanded='false' aria-controls='{notes_id}'>Détails</button></td>"
    )
    parts.append("</tr>")
    # Sous-ligne pleine largeur repliée : le détail pousse verticalement,
    # sans jamais masquer l'en-tête du jour suivant (pattern liste-matchs-dense).
    parts.append(f"<tr class='note-row' id='{notes_id}' hidden><td colspan='6'><ul class='note-list'>")
    if r.get("mpp_base_points") is not None:
        # Score, confiance et points décrivent tous le pick LIVE (predicted_score_live) :
        # les coller au score figé quand il a bougé donnerait un couple incohérent
        # (le badge « Modifié » porte déjà l'écart figé → live).
        parts.append(
            f"<li>Prono Mon Petit Prono : {html.escape(r['predicted_score_live'])} — "
            f"issue à {r['mpp_pick_pct']}%, {r['mpp_base_points']} pts au barème si elle tombe.</li>"
        )
    else:
        parts.append(
            f"<li>Prono recommandé (optimise les points Mon Petit Prono) : {html.escape(r['predicted_score'])} ({r['score_conf']}%)</li>"
        )
    if r.get("mpp_upside"):
        up = r["mpp_upside"]
        parts.append(
            f"<li>Option à variance : {html.escape(up['label'])} {html.escape(up['score'])} — "
            f"issue moins probable ({up['p_outcome']}%), mais {up['base_points']} pts si elle tombe.</li>"
        )
    if r["mpp_differs"]:
        parts.append(
            f"<li>Score le plus probable du modèle : {html.escape(r['mpp_modal_score'])}</li>"
        )
    # Issue 1N2 la plus probable selon le modèle (transparence). L'indice Nutri
    # n'est PAS accolé ici : il note le pick MPP (qui peut être une autre issue),
    # pas ce favori modèle — l'y coller induirait deux issues sous une pastille.
    parts.append(
        f"<li>Issue 1N2 la plus probable (modèle) : {html.escape(r['pick_label'])} ({round(r['pick_prob'] * 100)}%)</li>"
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
    if r["odds"]:
        parts.append(
            f"<li>Cotes bookmaker chargées : 1 {r['odds'][0]:.2f} / N {r['odds'][1]:.2f} / 2 {r['odds'][2]:.2f}</li>"
        )
    for vs in r["value_summaries"]:
        parts.append(f"<li>{html.escape(vs)}</li>")
    for note in r["notes"]:
        parts.append(f"<li>{html.escape(note)}</li>")
    parts.append("</ul></td></tr>")
    return parts


# Forme singulier/pluriel des compteurs du récap.
_RECAP_LABELS = {
    "exact": ("exact", "exacts"),
    "bon": ("bon", "bons"),
    "erreur": ("erreur", "erreurs"),
}
# En dessous de ce nombre de matchs comptés, on ne laisse pas la barre conclure
# seule : avertissement « échantillon réduit » + barre atténuée (pattern
# recap-justesse-pronos, garde-fou petit N).
_RECAP_SMALL_N = 5


def _render_recap(past_rows: List[Dict]) -> List[str]:
    """Récap cumul-tournoi de la justesse des pronos figés (exact/bon/erreur).

    Comptage descriptif a posteriori, jamais une note de certitude : la sortie
    du modèle reste une distribution de probabilités calibrée.
    """
    counts = common.tally_pronos(r.get("verdict") for r in past_rows)
    total = counts["total"]
    if total == 0:
        # Des matchs sont joués mais aucun prono n'avait été figé avant le coup
        # d'envoi : rien à comparer honnêtement.
        return [
            "<section class='panel recap'>",
            "<div class='recap-head'><h2>Justesse des pronos</h2></div>",
            "<p class='recap-note'>Aucun prono figé avant match à comparer pour l'instant. "
            "Lancez <code>python3 tools/snapshot_predictions.py</code> avant les coups d'envoi "
            "pour suivre la justesse réel vs prono.</p>",
            "</section>",
        ]

    def _count_label(cat: str) -> str:
        n = counts[cat]
        sing, plur = _RECAP_LABELS[cat]
        return f"<strong>{n}</strong> {sing if n <= 1 else plur}"

    sample = f"{total} match{'s' if total > 1 else ''} terminé{'s' if total > 1 else ''}"
    aria = (f"{counts['exact']} exacts, {counts['bon']} bons, {counts['erreur']} erreurs "
            f"sur {sample}")

    # Liste des matchs par catégorie : alimente le tooltip au survol (data-tip)
    # et l'aria-label (lecteurs d'écran). Pas de title natif (double tooltip).
    by_cat: Dict[str, List[str]] = {c: [] for c in common.PRONO_CATEGORIES}
    for r in past_rows:
        v = r.get("verdict")
        if v in by_cat:
            by_cat[v].append(f"{r['home_label']}–{r['away_label']}")

    def _cat_tip(cat: str) -> str:
        label = {"exact": "Exacts", "bon": "Bons résultats", "erreur": "Erreurs"}[cat]
        matches = " · ".join(by_cat[cat]) if by_cat[cat] else "aucun"
        return html.escape(f"{label} : {matches}")

    segs = []
    for cat in common.PRONO_CATEGORIES:
        if counts[cat]:
            # flex-grow proportionnel au compte : largeurs exactes, zéro filet
            # blanc d'arrondi en bout de barre. data-tip = liste pour le tooltip.
            segs.append(
                f"<span class='recap-seg recap-seg-{cat}' style='flex:{counts[cat]}' "
                f"data-tip='{_cat_tip(cat)}' aria-label='{_cat_tip(cat)}'></span>"
            )

    legend = []
    for cat in common.PRONO_CATEGORIES:
        # Survol de la légende = même tooltip que la barre (cible plus large).
        attrs = f"data-tip='{_cat_tip(cat)}' aria-label='{_cat_tip(cat)}'" if counts[cat] else ""
        legend.append(
            f"<li {attrs}><span class='swatch swatch-{cat}'></span> {_count_label(cat)}</li>"
        )

    small = total < _RECAP_SMALL_N
    section_cls = "panel recap recap-small" if small else "panel recap"
    out = [
        f"<section class='{section_cls}' aria-labelledby='recap-title'>",
        "<div class='recap-head'>",
        "<h2 id='recap-title'>Justesse des pronos</h2>",
        f"<span class='recap-sample'>sur {html.escape(sample)}</span>",
        "</div>",
        f"<div class='recap-bar' role='img' aria-label='{html.escape(aria)}'>",
        "".join(segs),
        "</div>",
        "<ul class='recap-legend'>",
        "".join(legend),
        "</ul>",
    ]
    if small:
        out.append(
            "<p class='recap-caveat'>Échantillon réduit — trop tôt pour conclure quoi que ce soit.</p>"
        )
    out.append(
        "<p class='recap-note'>Comptage descriptif des pronos figés avant match, pas une note de "
        "fiabilité du modèle — sa sortie reste une distribution de probabilités, pas un score sûr.</p>"
    )
    out.append("</section>")
    return out


def _render_page(rows: List[Dict], recommendations: Optional[Dict], error: str = "",
                 tab: str = "matchs", health: Optional[Dict] = None,
                 solidity_report: Optional[Dict] = None, data_info: Optional[Dict] = None,
                 bankroll: float = 50.0, bets: Optional[List[Dict]] = None) -> bytes:
    safe_tab = tab if tab in _TAB_LABELS else "matchs"

    past_rows = [r for r in rows if r.get("completed")]
    future_rows = [r for r in rows if not r.get("completed")]
    health_meta = _health_level_ui(str((health or {}).get("level", "")))
    bet_blocked = health_meta["can_bet"] != "1"
    n_changed = sum(1 for r in future_rows if r.get("prediction_changed"))

    parts = [
        "<!doctype html>",
        "<html lang='fr'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Pronos CM2026 — {_TAB_LABELS[safe_tab]}</title>",
        "<style>",
        _CSS,
        "</style></head><body><div class='app'>",
    ]
    parts.extend(_render_sidebar(safe_tab, health, health_meta,
                                 len(future_rows), len(past_rows), n_changed))
    parts.append("<main class='canvas'>")

    if error:
        parts.append(
            f"<div class='err' role='alert'>{html.escape(error)} "
            "<a href='/?tab=matchs'>Voir tous les matchs</a></div>"
        )
    if (health or {}).get("level") != "good":
        parts.append(f"<div class='guard-msg' style='margin-top:0'>{html.escape(health_meta['message'])}</div>")

    if safe_tab == "paris":
        parts.append("<div class='topbar'><div><h1>Paris</h1>"
                     "<p class='subtitle'>Suivi des paris réels en tête, puis recommandations prudentes calculées à partir du modèle et des cotes bookmaker.</p></div></div>")
        # Suivi des paris réels (argent engagé) en tête de page : c'est ce que
        # Baptiste vient consulter en premier. Indépendant du modèle/des cotes
        # (donnée historique), donc affiché même si la reco est bloquée.
        parts.extend(_render_suivi_paris(bets or []))
        parts.extend(_render_paris(recommendations, bankroll, bet_blocked,
                                   placed_picks=_placed_picks(bets)))

    elif safe_tab == "diagnostics":
        parts.append("<div class='topbar'><div><h1>Diagnostics</h1>"
                     "<p class='subtitle'>Qualité des données &amp; solidité du modèle — à consulter avant de faire confiance aux pronos.</p></div></div>")
        # _render_diagnostics émet déjà ses propres .panel — pas de wrapper
        # (sinon bordure dans bordure).
        diag_chunk = _render_diagnostics(health, health_meta, solidity_report, data_info)
        if diag_chunk:
            parts.extend(diag_chunk)
        else:
            parts.append("<div class='panel'><div class='muted'>Diagnostics indisponibles pour le moment.</div></div>")

    else:  # matchs : passés (repliés) puis futurs, ordre chronologique
        parts.append(
            "<div class='topbar'>"
            "<div><h1>Matchs</h1>"
            "<p class='subtitle'>Chaque match porte un <strong>verdict</strong> — favori solide, "
            "léger, piège (nul probable) ou pile ou face — pour voir d'un coup <strong>sur quel "
            "favori ne PAS miser</strong>. Distribution 1·N·2 et confiance <strong>A</strong>&rarr;<strong>E</strong> "
            "à l'appui ; le score reste en second (pour MPP).</p></div>"
            "<div class='filter-wrap'>"
            "<label class='sr-only' for='country-filter'>Filtrer par pays</label>"
            "<input id='country-filter' class='country-filter' type='search' "
            "placeholder='Filtrer par pays…' autocomplete='off' spellcheck='false'>"
            "<span class='filter-count' id='filter-count' aria-live='polite'></span>"
            "</div>"
            "</div>"
        )
        parts.append(
            "<div class='no-results' id='no-results' hidden role='status'>Aucun match pour ce pays. "
            "<button type='button' class='link-btn' id='clear-filter'>Effacer le filtre</button></div>"
        )
        # Passés d'abord (chronologie). Le récap Justesse reste TOUJOURS visible
        # (hors disclosure) ; seule la liste des matchs passés est repliable.
        if past_rows:
            n_past = len(past_rows)
            parts.extend(_render_recap(past_rows))
            parts.append("<div id='recap-tip' class='recap-tip' role='tooltip' hidden></div>")
            parts.append("<details class='past-disclosure' id='past-disclosure'>")
            parts.append(
                f"<summary class='past-summary'>"
                f"<span class='past-label'>Matchs passés <span class='past-count'>{n_past}</span></span>"
                f"<span class='past-hint'>afficher / masquer</span></summary>"
            )
            parts.append("<div class='past-body'>")
            parts.extend(_render_past_table(past_rows))
            parts.append("</div></details>")

        if future_rows:
            vc = _verdict_counts(future_rows)
            watch = vc["serre"] + vc["piege"] + vc["ouvert"]
            n_sol = vc["solide"]
            sol_txt = f"{n_sol} favori solide" if n_sol == 1 else f"{n_sol} favoris solides"
            details = []
            if vc["piege"]:
                details.append(f"{vc['piege']} piège{'s' if vc['piege'] > 1 else ''}-nul")
            if vc["ouvert"]:
                details.append(f"{vc['ouvert']} pile ou face")
            if vc["serre"]:
                details.append(f"{vc['serre']} serré{'s' if vc['serre'] > 1 else ''}")
            note = (f"<span class='cs-note'>dont {html.escape(', '.join(details))}</span>"
                    if details else "")
            parts.append(
                "<div class='conf-summary' role='status'>"
                f"<span class='cs-chip cs-solide'>{html.escape(sol_txt)}</span>"
                f"<span class='cs-chip cs-watch'>{watch} à examiner</span>"
                f"{note}"
                "</div>"
            )
            parts.extend(_render_day_sections(_group_rows_by_matchday(future_rows), past=False))
        else:
            parts.append("<div class='panel'><div class='muted'>Aucun match à venir à afficher.</div></div>")

    parts.append("</main></div>")
    parts.extend([
        "<script>",
        "(function(){",
        # Accordéon « Détails » des lignes futures.
        "document.querySelectorAll('.details-btn').forEach(function(btn){",
        "btn.addEventListener('click',function(){",
        "var t=document.getElementById(btn.getAttribute('aria-controls'));",
        "if(!t){return;}",
        "var open=t.hasAttribute('hidden');",
        "if(open){t.removeAttribute('hidden');}else{t.setAttribute('hidden','');}",
        "btn.setAttribute('aria-expanded',open?'true':'false');",
        "});});",
        # Repli des passés : persistance entre visites (défaut serveur = replié).
        "var past=document.getElementById('past-disclosure');",
        "if(past){var PK='wc2026_past_open_v1';",
        "try{if(localStorage.getItem(PK)==='1'){past.open=true;}}catch(e){}",
        "past.addEventListener('toggle',function(){try{localStorage.setItem(PK,past.open?'1':'0');}catch(e){}});}",
        # Filtre pays instantané (futurs + passés).
        "var input=document.getElementById('country-filter');",
        "if(input){",
        "var countEl=document.getElementById('filter-count');",
        "var noRes=document.getElementById('no-results');",
        "var clearBtn=document.getElementById('clear-filter');",
        "var rows=Array.prototype.slice.call(document.querySelectorAll('.match-row'));",
        "var apply=function(){",
        "var q=input.value.trim().toLowerCase();var visible=0,pastHit=0;",
        "rows.forEach(function(tr){",
        "var hit=!q||(tr.getAttribute('data-search')||'').indexOf(q)>=0;",
        "tr.style.display=hit?'':'none';",
        "var nr=tr.nextElementSibling;",
        "if(nr&&nr.classList.contains('note-row')){nr.style.display=hit?'':'none';}",
        "if(hit){visible++;if(past&&past.contains(tr)){pastHit++;}}",
        "});",
        # Masquer les sections-jour vidées par le filtre (pas d'en-tête trompeur).
        "document.querySelectorAll('.day-section').forEach(function(sec){",
        "var vis=false;sec.querySelectorAll('.match-row').forEach(function(r){if(r.style.display!=='none'){vis=true;}});",
        "sec.style.display=vis?'':'none';});",
        # Un match passé qui matche derrière un repli : on déplie pour ne pas le perdre.
        "if(past&&q&&pastHit>0){past.open=true;}",
        "countEl.textContent=q?(visible+' match'+(visible>1?'s':'')+' \\u00b7 \\u00ab '+input.value.trim()+' \\u00bb'):'';",
        "noRes.hidden=!(q&&visible===0);",
        "};",
        "input.addEventListener('input',apply);",
        "if(clearBtn){clearBtn.addEventListener('click',function(){input.value='';apply();input.focus();});}",
        "}",
        # Survol du chart Justesse (segment ou légende) : surligne les matchs
        # de la catégorie dans la liste des passés juste en dessous.
        # Survol du chart Justesse (segment ou légende) : petit tooltip listant
        # les matchs de la catégorie. N'ouvre rien, ne déplace rien.
        "var tip=document.getElementById('recap-tip');",
        "document.querySelectorAll('[data-tip]').forEach(function(el){",
        "var show=function(){if(!tip){return;}tip.textContent=el.getAttribute('data-tip');tip.hidden=false;",
        "var r=el.getBoundingClientRect();var x=Math.max(8,r.left);",
        "x=Math.min(x,window.innerWidth-tip.offsetWidth-8);",
        "var y=r.top-tip.offsetHeight-8;if(y<8){y=r.bottom+8;}",
        "tip.style.left=Math.round(x)+'px';tip.style.top=Math.round(y)+'px';};",
        "var hide=function(){if(tip){tip.hidden=true;}};",
        "el.addEventListener('mouseenter',show);el.addEventListener('mouseleave',hide);",
        "el.addEventListener('focus',show);el.addEventListener('blur',hide);",
        "});",
        "})();",
        "</script>",
        "</body></html>",
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
    tab = (params.get("tab") or "matchs").strip().lower() or "matchs"
    # Back-compat : les anciens onglets séparés Futurs/Passés sont désormais
    # fusionnés dans la vue Matchs unique.
    if tab in ("futurs", "passes"):
        tab = "matchs"
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
        # eloratings.net already moves Elo with match results, and so does
        # apply_completed_results below. Running both would count each result
        # twice, so the live overlay only tracks Elo *before* the tournament
        # starts; once any fixture is completed, the committed baseline + local
        # result deltas are the single (transparent) source of in-tournament
        # movement.
        if not any(_is_completed(m) for m in fixtures):
            ratings, _ = live_ratings.ensure(ratings)   # pre-tournament: keep Elo fresh on read-only hosts (Vercel)
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
                        solidity_report=solidity_report, data_info=data_info,
                        bankroll=bankroll, bets=data.load_bets())


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
