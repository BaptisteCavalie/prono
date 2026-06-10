from pathlib import Path
import sys

from flask import Flask, Response, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui

app = Flask(__name__)


@app.get("/")
def home():
    matchday = (request.args.get("matchday", "") or "").strip()
    date_value = (request.args.get("date", "") or "").strip()
    odds_file = (request.args.get("odds_file", "") or "").strip()
    action = (request.args.getlist("action")[-1] if request.args.getlist("action") else "refresh").strip().lower()
    tab = (request.args.get("tab", "futurs") or "futurs").strip().lower()
    if action == "reco":
        tab = "paris"
    no_auto = (request.args.get("no_auto", "") or "") in ("1", "on", "true")
    try:
        bankroll = float((request.args.get("bankroll", "50") or "50").strip())
    except ValueError:
        bankroll = 50.0
    if bankroll <= 0:
        bankroll = 50.0

    body = ui._process_request(matchday, date_value, odds_file, no_auto, tab, bankroll, action)
    resp = Response(body, mimetype="text/html; charset=utf-8")
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.get("/<path:_rest>")
def fallback(_rest: str):
    return Response("Not found", status=404)


# Vercel entrypoint
handler = app
