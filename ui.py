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

from engine import data, model, odds as oddsmod, strategies, updater

ROOT = Path(__file__).resolve().parent


def _split_match(s: str):
    for sep in (" vs ", " VS ", " v ", "/", " - "):
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return None


def _parse_date(s: str):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


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


def _analyse_rows(fixtures: List[Dict], ratings: Dict, odds_board: Dict[str, List[float]]):
    rows = []
    for m in fixtures:
        home = m["home"]
        away = m["away"]
        rh = ratings["teams"][home]
        ra = ratings["teams"][away]
        out = model.analyse(rh["rating"], ra["rating"], home_adv=m.get("home_adv", 0.0))
        pick_sel, pick_label, pick_prob = _best_selection(home, away, out)

        (si, sj), sp = out["top_scores"][0]
        predicted_score = f"{si}-{sj}"
        est = rh.get("source") != "live" or ra.get("source") != "live"
        completed = _is_completed(m)
        actual_score = None
        if completed:
            actual_score = f"{m.get('actual_home')}-{m.get('actual_away')}"

        odds = _find_match_odds(m, odds_board)
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
        if est:
            notes.append("Au moins une cote Elo est estimee. Le niveau de confiance peut bouger apres mise a jour live.")
        if not odds:
            notes.append("Aucune cote chargee. Ajoute un fichier JSON de cotes pour activer la detection de value.")
        elif not value_summaries:
            notes.append("Aucune opportunite EV positive detectee contre les cotes actuelles.")

        pick_is_draw = pick_sel == "draw"
        top_score_is_draw = si == sj
        if pick_is_draw != top_score_is_draw:
            notes.append(
                "Important: le score exact le plus probable peut etre different du meilleur pari 1X2. "
                "Le score exact est un seul scenario, alors que le pari 1X2 additionne plusieurs scenarios."
            )

        if completed:
            notes.append("Match termine: le score affiche est le score reel final.")

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
            "score_conf": round(sp * 100),
            "predicted_score": predicted_score,
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
            "nutri": _confidence_nutriscore(pick_prob, est),
            "completed": completed,
            "est": est,
        })
    return rows


def _group_rows_by_matchday(rows: List[Dict]):
    grouped: Dict[int, List[Dict]] = {}
    for r in rows:
        md = int(r.get("matchday") or 0)
        grouped.setdefault(md, []).append(r)
    return sorted(grouped.items(), key=lambda kv: kv[0])


def _build_recommendations(rows: List[Dict]):
    future_rows = [r for r in rows if not r.get("completed")]
    if not future_rows:
        return None

    candidates = []
    for r in future_rows:
        candidates.append({
            "match_id": r["id"],
            "home": r["home"],
            "away": r["away"],
            "pick": r["pick_label"],
            "prob": r["pick_prob"],
            "odds": r["pick_odds"],
            "nutri": r["nutri"],
        })

    singles = [c for c in candidates if c["nutri"] in ("A", "B", "C")]
    if not singles:
        singles = candidates[:10]
    else:
        singles = singles[:10]

    combos_a_source = [c for c in candidates if c["nutri"] == "A"]
    combos_a = []
    for i in range(0, max(0, len(combos_a_source) - 1)):
        c1 = combos_a_source[i]
        c2 = combos_a_source[i + 1]
        pair = [c1, c2]
        odds_ok = c1["odds"] is not None and c2["odds"] is not None
        combined_odds = (c1["odds"] * c2["odds"]) if odds_ok else None
        combined_prob = c1["prob"] * c2["prob"]
        combos_a.append({
            "legs": pair,
            "combined_odds": combined_odds,
            "combined_prob": combined_prob,
        })
        if len(combos_a) >= 6:
            break

    if len(combos_a_source) >= 3:
        triple = combos_a_source[:3]
        odds_ok = all(x["odds"] is not None for x in triple)
        combined_odds = (triple[0]["odds"] * triple[1]["odds"] * triple[2]["odds"]) if odds_ok else None
        combined_prob = triple[0]["prob"] * triple[1]["prob"] * triple[2]["prob"]
        combos_a.append({
            "legs": triple,
            "combined_odds": combined_odds,
            "combined_prob": combined_prob,
        })

    return {
        "singles": singles,
        "combos_a": combos_a,
        "has_full_odds": any(c["odds"] is not None for c in candidates),
    }


def _render_page(matchday: str, date_value: str, odds_file: str, no_auto: bool,
                 rows: List[Dict], applied_results: int, action: str,
                 recommendations: Optional[Dict], error: str = "", tab: str = "futurs") -> bytes:
    safe_tab = "passes" if tab == "passes" else "futurs"
    title_tag = "Calendrier"

    past_rows = [r for r in rows if r.get("completed")]
    future_rows = [r for r in rows if not r.get("completed")]
    shown_rows = past_rows if safe_tab == "passes" else future_rows
    grouped = _group_rows_by_matchday(shown_rows)

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
        ".panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:12px 12px 10px;margin-bottom:12px;box-shadow:0 8px 26px rgba(24,37,66,.06)}",
        ".actions{display:flex;justify-content:flex-end}",
        "button{width:100%;min-height:43px;padding:10px 14px;border-radius:10px;border:0;background:var(--brand);color:var(--brand-ink);font:700 .9rem/1.1 'Trebuchet MS','Gill Sans','Avenir Next',sans-serif;cursor:pointer}",
        "button.alt{background:linear-gradient(135deg,#f0a53d,#d9801f);color:#1e1406}",
        "button:hover{filter:brightness(1.06)}",
        "input:focus-visible,button:focus-visible{outline:3px solid color-mix(in srgb,var(--brand) 40%,white);outline-offset:2px}",
        ".stats{display:flex;gap:8px;flex-wrap:wrap}",
        ".stamp{background:var(--surface-2);border:1px solid var(--line);border-radius:999px;padding:6px 10px;font-size:.78rem;color:var(--muted)}",
        "table{width:100%;border-collapse:collapse}",
        "th,td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:middle}",
        "th{text-align:left;font-size:.69rem;color:var(--muted);text-transform:uppercase;letter-spacing:.11em}",
        "td strong{font-weight:700}",
        ".nutri{display:inline-block;min-width:28px;text-align:center;padding:3px 7px;border-radius:999px;font-weight:700;font-size:.75rem;color:#fff;margin-left:6px}",
        ".nutri-a{background:#168a3d}",
        ".nutri-b{background:#4ea93a}",
        ".nutri-c{background:#d4a813}",
        ".nutri-d{background:#d37a1c}",
        ".nutri-e{background:#b33a2f}",
        ".md-title{display:flex;justify-content:space-between;gap:8px;align-items:center;margin:2px 2px 6px}",
        ".matchline{display:flex;align-items:center;gap:6px;font-size:.95rem;line-height:1.15}",
        ".line-main{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap}",
        ".line-left{display:flex;align-items:center;gap:8px;flex-wrap:wrap}",
        ".line-right{display:flex;align-items:center;gap:8px;flex-wrap:wrap}",
        ".flag{font-size:1.05rem}",
        ".tiny{font-size:.76rem;color:var(--muted)}",
        ".result-main{font-weight:700}",
        ".result-sub{font-size:.82rem;color:var(--muted)}",
        "details{border:1px solid var(--line);border-radius:10px;padding:5px 8px;background:#fbfdff}",
        "summary{cursor:pointer;font-size:.82rem;color:var(--brand);font-weight:700}",
        "summary::marker{color:var(--brand)}",
        ".note-list{margin:6px 0 0;padding-left:16px;color:var(--muted);font-size:.8rem;line-height:1.3}",
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
        "@media (max-width:860px){.reco-grid{grid-template-columns:1fr}.modal-columns{grid-template-columns:1fr}}",
        "@media (max-width:760px){.wrap{padding:16px 12px 26px}.panel{padding:11px 10px}.actions{margin-top:2px}table thead{display:none}table,tbody,tr,td{display:block;width:100%}tr{border:1px solid var(--line);border-radius:12px;padding:8px 9px;margin-bottom:8px;background:var(--surface)}td{border:0;padding:4px 0}td::before{content:attr(data-label);display:block;color:var(--muted);font-size:.7rem;letter-spacing:.06em;text-transform:uppercase;margin-bottom:2px}}",
        "</style></head><body><main class='wrap'>",
        "<header class='mast'>",
        "<div>",
        f"<h1>WC2026 Calendrier Pronos - {html.escape(title_tag)}</h1>",
        "<p class='subtitle'>Vue compacte calendrier. Ouvre les accordions pour les details importants uniquement.</p>",
        "</div>",
        "<div class='stats'>",
        f"<div class='stamp'>Resultats appliques automatiquement: {applied_results}</div>",
        f"<div class='stamp'>Futurs: {len(future_rows)}</div>",
        f"<div class='stamp'>Passes: {len(past_rows)}</div>",
        "</div>",
        "</header>",
    ]

    if error:
        parts.append(f"<div class='err'>{html.escape(error)}</div>")

    parts.extend([
        "<div class='panel'>",
        "<form method='get' action='/' aria-label='Actions calendrier'>",
        f"<input type='hidden' name='tab' value='{safe_tab}'>",
        "<div class='actions'><button class='alt' type='submit' name='action' value='reco'>Generer les paris (single 10EUR + combine 1EUR)</button></div>",
        "</form>",
        "<div class='actions' style='justify-content:flex-start;gap:8px;margin-top:10px'>",
        f"<a href='/?tab=futurs' class='stamp' style='text-decoration:none;{('background:#d9f0ff;border-color:#8db8d1;color:#11384d' if safe_tab == 'futurs' else '')}'>Futurs</a>",
        f"<a href='/?tab=passes' class='stamp' style='text-decoration:none;{('background:#d9f0ff;border-color:#8db8d1;color:#11384d' if safe_tab == 'passes' else '')}'>Passes</a>",
        "</div>",
        "<div class='legend'>Date inconnue = date absente dans les donnees. Ici, une date est toujours affichee.</div>",
        "</div>",
    ])

    if recommendations and action == "reco":
        singles = recommendations.get("singles", [])
        combos_a = recommendations.get("combos_a", [])
        parts.extend([
            "<div id='reco-modal' class='modal' role='dialog' aria-modal='true' aria-labelledby='reco-title'>",
            "<div class='modal-panel'>",
            "<div class='modal-head'>",
            "<h2 id='reco-title' style='margin:0'>Propositions de paris</h2>",
            "<button type='button' class='modal-close' id='close-reco'>Fermer</button>",
            "</div>",
            "<div class='modal-columns'>",
            "<section class='reco-card'>",
            "<h3>Paris uniques - mise 10 EUR</h3>",
            "<div class='bet-list'>",
        ])
        if singles:
            for s in singles:
                parts.append("<article class='bet-item'>")
                parts.append(f"<div class='bet-title'>{html.escape(s['match_id'])} - {html.escape(s['home'])} vs {html.escape(s['away'])}</div>")
                parts.append(f"<div>{html.escape(s['pick'])} - {round(s['prob'] * 100)}% (Nutri {html.escape(s['nutri'])})</div>")
                if s.get("odds"):
                    parts.append(f"<div class='bet-meta'>Cote {s['odds']:.2f} - retour brut potentiel: {10 * s['odds']:.2f} EUR</div>")
                else:
                    parts.append("<div class='bet-meta'>Cote indisponible</div>")
                parts.append("</article>")
        else:
            parts.append("<div class='muted'>Aucun pari unique propose.</div>")

        parts.extend([
            "</div>",
            "</section>",
            "<section class='reco-card'>",
            "<h3>Combines Nutri A - mise 1 EUR</h3>",
            "<div class='bet-list'>",
        ])
        if combos_a:
            for c in combos_a:
                parts.append("<article class='bet-item'>")
                legs = c.get("legs", [])
                for idx, leg in enumerate(legs, start=1):
                    parts.append(
                        f"<div><strong>Sel. {idx}</strong>: {html.escape(leg['pick'])} ({html.escape(leg['home'])} vs {html.escape(leg['away'])}) - {round(leg['prob'] * 100)}%</div>"
                    )
                if c.get("combined_odds"):
                    parts.append(f"<div class='bet-meta'>Cote combinee: {c['combined_odds']:.2f} - retour brut potentiel: {c['combined_odds']:.2f} EUR</div>")
                else:
                    parts.append("<div class='bet-meta'>Cote combinee indisponible (odds manquantes)</div>")
                parts.append(f"<div class='bet-meta'>Probabilite combinee modele: {round(c['combined_prob'] * 100)}%</div>")
                parts.append("</article>")
        else:
            parts.append("<div class='muted'>Aucun combine Nutri A disponible actuellement.</div>")

        if not recommendations.get("has_full_odds"):
            parts.append("<div class='muted'>Astuce: ajoute un fichier de cotes pour des retours exacts.</div>")

        parts.extend([
            "</div>",
            "</section>",
            "</div>",
            "</div>",
            "</div>",
            "<script>",
            "(function(){",
            "const modal=document.getElementById('reco-modal');",
            "if(!modal){return;}",
            "modal.classList.add('open');",
            "const closeBtn=document.getElementById('close-reco');",
            "const close=()=>modal.classList.remove('open');",
            "if(closeBtn){closeBtn.addEventListener('click',close);}",
            "modal.addEventListener('click',(e)=>{if(e.target===modal){close();}});",
            "document.addEventListener('keydown',(e)=>{if(e.key==='Escape'){close();}});",
            "})();",
            "</script>",
        ])

    if not shown_rows:
        if safe_tab == "passes":
            parts.extend(["<div class='panel'><div class='muted'>Aucun match passe avec score final renseigne pour le moment.</div></div>"])
        else:
            parts.extend(["<div class='panel'><div class='muted'>Aucun match futur a afficher.</div></div>"])

    for md, md_rows in grouped:
        parts.extend([
            "<section class='panel'>",
            "<div class='md-title'>",
            f"<strong>Journee {md}</strong>",
            f"<span class='tiny'>{len(md_rows)} matchs</span>",
            "</div>",
            "<table><thead><tr>",
            "<th>Date</th><th>Match + Resultat + Nutri</th><th>Infos</th>",
            "</tr></thead><tbody>",
        ])

        for r in md_rows:
            est = " *" if r["est"] else ""
            date_tag = r["date"][:10]
            score_suffix = " (final)" if r["completed"] else f" ({r['score_conf']}%){est}"
            parts.append("<tr>")
            parts.append(
                f"<td data-label='Date'><div class='tiny'>{html.escape(date_tag)}</div>"
                f"<div class='tiny'>J{html.escape(str(r['matchday']))} · Groupe {html.escape(str(r['group']))} · {html.escape(str(r['id']))}</div></td>"
            )
            parts.append(
                f"<td data-label='Match + Resultat + Nutri'><div class='line-main'><div class='line-left'>"
                f"<div class='matchline'><span class='flag'>{r['home_flag']}</span><strong>{html.escape(r['home'])}</strong>"
                f"<span class='tiny'>vs</span><span class='flag'>{r['away_flag']}</span><strong>{html.escape(r['away'])}</strong></div>"
                f"</div><div class='line-right'><span class='result-main'>{html.escape(r['score'])}"
                f"{score_suffix}</span>"
                f"<span class='nutri nutri-{html.escape(r['nutri'].lower())}'>{html.escape(r['nutri'])}</span></div></div></td>"
            )

            parts.append("<td data-label='Infos'><details><summary>Infos importantes</summary><ul class='note-list'>")
            parts.append(
                f"<li>Probas 1X2 modele: 1={r['p_home']}% | N={r['p_draw']}% | 2={r['p_away']}%</li>"
            )
            parts.append(
                f"<li>Pick principal: {html.escape(r['pick_label'])} ({round(r['pick_prob'] * 100)}%), Nutri {html.escape(r['nutri'])}</li>"
            )
            parts.append(
                f"<li>Recommandation de pari: {html.escape(r['bet'])} ({r['bet_conf']}%{est})</li>"
            )
            if r["completed"]:
                parts.append(f"<li>Score predit avant match: {html.escape(r['predicted_score'])} ({r['score_conf']}%)</li>")
            if r["odds"]:
                parts.append(
                    f"<li>Cotes chargees: 1 {r['odds'][0]:.2f} / N {r['odds'][1]:.2f} / 2 {r['odds'][2]:.2f}</li>"
                )
            for vs in r["value_summaries"]:
                parts.append(f"<li>{html.escape(vs)}</li>")
            for note in r["notes"]:
                parts.append(f"<li>{html.escape(note)}</li>")
            parts.append("</ul></details></td>")
            parts.append("</tr>")

        parts.extend(["</tbody></table>", "</section>"])

    parts.extend(["</main></body></html>"])
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
        no_auto = (params.get("no_auto", [""])[0] or "") in ("1", "on", "true")

        rows = []
        applied_results = 0
        error = ""
        recommendations = None

        try:
            fixtures = data.load_fixtures()
            ratings = data.load_ratings()
            if not no_auto:
                ratings, applied_results = updater.apply_completed_results(ratings, fixtures)

            selected = _select_fixtures(fixtures, date_value, matchday)
            if not selected:
                if date_value:
                    error = f"Aucun match trouve pour la date {date_value}."
                else:
                    error = f"Aucun match trouve pour la journee {matchday}."
            odds_board = _load_odds_board(odds_file)
            rows = _analyse_rows(selected, ratings, odds_board)
            if action == "reco":
                recommendations = _build_recommendations(rows)
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
