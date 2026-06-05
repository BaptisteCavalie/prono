#!/usr/bin/env python3
"""Local web UI for the WC2026 prediction engine (stdlib only)."""
from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from engine import data, model, odds as oddsmod, updater

ROOT = Path(__file__).resolve().parent


def _split_match(s: str):
    for sep in (" vs ", " VS ", " v ", "/", " - "):
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return None


def _parse_date(s: str):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


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
    if date_value:
        target = _parse_date(date_value)
        selected = [m for m in fixtures if m.get("date") and _parse_date(m["date"]) == target]
        return selected

    try:
        md = int(matchday or "1")
    except ValueError:
        md = 1

    return [m for m in fixtures if m.get("matchday") == md]


def _analyse_rows(fixtures: List[Dict], ratings: Dict, odds_board: Dict[str, List[float]]):
    rows = []
    for m in fixtures:
        home = m["home"]
        away = m["away"]
        rh = ratings["teams"][home]
        ra = ratings["teams"][away]
        out = model.analyse(rh["rating"], ra["rating"], home_adv=m.get("home_adv", 0.0))

        (si, sj), sp = out["top_scores"][0]
        est = rh.get("source") != "live" or ra.get("source") != "live"

        odds = _find_match_odds(m, odds_board)
        bet_label = ""
        bet_conf = 0

        if odds:
            value_rows = oddsmod.value_1x2(out, odds[0], odds[1], odds[2])
            value_candidates = [r for r in value_rows if r["value"]]
            if value_candidates:
                best = max(value_candidates, key=lambda r: r["ev"])
                bet_label = {
                    "home": f"{home} win @ {best['odds']:.2f}",
                    "draw": f"Draw @ {best['odds']:.2f}",
                    "away": f"{away} win @ {best['odds']:.2f}",
                }[best["sel"]]
                bet_conf = round(best["model"] * 100)
            else:
                pick = max(
                    ((f"{home} win", out["p_home"]), ("Draw", out["p_draw"]), (f"{away} win", out["p_away"])),
                    key=lambda x: x[1],
                )
                bet_label = f"{pick[0]} (no value vs odds)"
                bet_conf = round(pick[1] * 100)
        else:
            pick = max(
                ((f"{home} win", out["p_home"]), ("Draw", out["p_draw"]), (f"{away} win", out["p_away"])),
                key=lambda x: x[1],
            )
            bet_label = pick[0]
            bet_conf = round(pick[1] * 100)

        rows.append({
            "id": m.get("id", ""),
            "group": m.get("group", "?"),
            "matchday": m.get("matchday", "?"),
            "home": home,
            "away": away,
            "score": f"{si}-{sj}",
            "score_conf": round(sp * 100),
            "bet": bet_label,
            "bet_conf": bet_conf,
            "est": est,
        })

    rows.sort(key=lambda r: r["id"])
    return rows


def _render_page(matchday: str, date_value: str, odds_file: str, no_auto: bool,
                 rows: List[Dict], applied_results: int, error: str = "") -> bytes:
    safe_matchday = html.escape(matchday or "")
    safe_date = html.escape(date_value or "")
    safe_odds = html.escape(odds_file or "")

    title_tag = safe_date if safe_date else f"MD{safe_matchday or '1'}"

    parts = [
        "<!doctype html>",
        "<html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>WC2026 Daily Sheet</title>",
        "<style>",
        ":root{--bg:#f6f0e6;--surface:#fffdf8;--surface-2:#f3ebde;--text:#211f1b;--muted:#5f5a51;--line:#d8cfbf;--line-2:#c7bba8;--brand:#1c5b47;--brand-ink:#f6f0e6;--alert:#7f2430}",
        "*{box-sizing:border-box}",
        "body{font-family:'Palatino Linotype',Palatino,Book Antiqua,serif;margin:0;background:radial-gradient(circle at 15% 0%,#fef8ef 0,#f6f0e6 45%,#efe6d6 100%);color:var(--text)}",
        ".wrap{max-width:1180px;margin:0 auto;padding:24px 18px 36px}",
        ".mast{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:14px}",
        "h1{margin:0;font-size:clamp(1.45rem,2.2vw,2rem);letter-spacing:.2px;line-height:1.1}",
        ".subtitle{margin:4px 0 0;color:var(--muted);font-size:.95rem;max-width:62ch}",
        ".panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:14px 14px 10px;margin-bottom:14px;box-shadow:0 10px 30px rgba(34,30,20,.05)}",
        "form{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr)) auto;gap:10px;align-items:end}",
        ".field label{display:block;font-size:.78rem;margin-bottom:4px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}",
        "input[type='text'],input[type='number'],input[type='date']{width:100%;min-height:46px;padding:10px 12px;border-radius:10px;border:1px solid var(--line-2);background:var(--surface-2);font:inherit;color:var(--text)}",
        ".check{display:flex;gap:8px;align-items:center;min-height:46px;padding:10px 12px;border-radius:10px;border:1px solid var(--line-2);background:var(--surface-2)}",
        ".check label{margin:0;font-size:.86rem;color:var(--text);text-transform:none;letter-spacing:0}",
        "button{width:100%;min-height:46px;padding:10px 14px;border-radius:10px;border:0;background:var(--brand);color:var(--brand-ink);font:700 .92rem/1.1 'Palatino Linotype',Palatino,Book Antiqua,serif;cursor:pointer}",
        "button:hover{filter:brightness(1.05)}",
        "input:focus-visible,button:focus-visible{outline:3px solid color-mix(in srgb,var(--brand) 40%,white);outline-offset:2px}",
        "table{width:100%;border-collapse:collapse}",
        "th,td{padding:12px 9px;border-bottom:1px solid var(--line);vertical-align:top}",
        "th{text-align:left;font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.12em}",
        "td strong{font-weight:700}",
        ".muted{color:var(--muted);font-size:.9rem}",
        ".stamp{background:var(--surface-2);border:1px solid var(--line);border-radius:999px;padding:6px 11px;font-size:.78rem;color:var(--muted)}",
        ".err{background:var(--alert);color:#fff;padding:11px 12px;border-radius:10px;margin-bottom:10px}",
        ".legend{margin-top:8px;color:var(--muted);font-size:.84rem}",
        "@media (max-width:1000px){form{grid-template-columns:repeat(2,minmax(150px,1fr))}}",
        "@media (max-width:760px){.wrap{padding:16px 12px 26px}.panel{padding:12px 10px}form{grid-template-columns:1fr}.actions{margin-top:2px}table thead{display:none}table,tbody,tr,td{display:block;width:100%}tr{border:1px solid var(--line);border-radius:12px;padding:8px 9px;margin-bottom:10px;background:var(--surface)}td{border:0;padding:5px 0}td::before{content:attr(data-label);display:block;color:var(--muted);font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;margin-bottom:3px}}",
        "</style></head><body><main class='wrap'>",
        "<header class='mast'>",
        "<div>",
        f"<h1>WC2026 Daily Sheet - {html.escape(title_tag)}</h1>",
        "<p class='subtitle'>Probability guide only. Confidence percentages are model estimates, not guarantees.</p>",
        "</div>",
        f"<div class='stamp'>Auto-updated results applied: {applied_results}</div>",
        "</header>",
    ]

    if error:
        parts.append(f"<div class='err'>{html.escape(error)}</div>")

    parts.extend([
        "<div class='panel'>",
        "<form method='get' action='/' aria-label='Daily sheet filters'>",
        "<div class='field'><label for='matchday'>Matchday (1-3)</label>",
        f"<input id='matchday' name='matchday' type='number' min='1' max='3' value='{safe_matchday}' placeholder='1'></div>",
        "<div class='field'><label for='date'>Date (YYYY-MM-DD)</label>",
        f"<input id='date' name='date' type='date' value='{safe_date}' placeholder='2026-06-11'></div>",
        "<div class='field'><label for='odds_file'>Odds file (optional)</label>",
        f"<input id='odds_file' name='odds_file' type='text' value='{safe_odds}' placeholder='data/odds_md1.json'></div>",
        "<div class='field'><label for='no_auto'>Rating updates</label>",
        f"<div class='check'><input id='no_auto' name='no_auto' type='checkbox' value='1' {'checked' if no_auto else ''}><label for='no_auto'>Use frozen baseline ratings</label></div></div>",
        "<div class='actions'><button type='submit'>Refresh Sheet</button></div>",
        "</form>",
        "<div class='legend'>Date takes priority over matchday when both are set.</div>",
        "</div>",
        "<div class='panel'>",
        f"<div class='muted'>Matches: {len(rows)}</div>",
        "<table><thead><tr>",
        "<th>Game</th><th>Exact Score Guess</th><th>Bet Recommendation</th>",
        "</tr></thead><tbody>",
    ])

    for r in rows:
        est = "*" if r["est"] else ""
        parts.append("<tr>")
        parts.append(
            f"<td data-label='Game'><strong>{html.escape(r['home'])} vs {html.escape(r['away'])}</strong><br>"
            f"<span class='muted'>[{html.escape(str(r['group']))} MD{html.escape(str(r['matchday']))}] {est}</span></td>"
        )
        parts.append(
            f"<td data-label='Exact score guess'>{html.escape(r['score'])} - <strong>{r['score_conf']}%{est}</strong></td>"
        )
        parts.append(
            f"<td data-label='Bet recommendation'>{html.escape(r['bet'])} - <strong>{r['bet_conf']}%{est}</strong></td>"
        )
        parts.append("</tr>")

    parts.extend(["</tbody></table></div>", "</main></body></html>"])
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
        matchday = (params.get("matchday", ["1"])[0] or "1").strip()
        date_value = (params.get("date", [""])[0] or "").strip()
        odds_file = (params.get("odds_file", [""])[0] or "").strip()
        no_auto = (params.get("no_auto", [""])[0] or "") in ("1", "on", "true")

        rows = []
        applied_results = 0
        error = ""

        try:
            fixtures = data.load_fixtures()
            ratings = data.load_ratings()
            if not no_auto:
                ratings, applied_results = updater.apply_completed_results(ratings, fixtures)

            selected = _select_fixtures(fixtures, date_value, matchday)
            if not selected:
                if date_value:
                    error = f"No fixtures found for date {date_value}."
                else:
                    error = f"No fixtures found for matchday {matchday}."
            odds_board = _load_odds_board(odds_file)
            rows = _analyse_rows(selected, ratings, odds_board)
        except Exception as exc:
            error = str(exc)

        body = _render_page(matchday, date_value, odds_file, no_auto, rows, applied_results, error)
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
