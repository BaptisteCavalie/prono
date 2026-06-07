from pathlib import Path
import sys

from flask import Flask, Response, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import data, updater
import ui

app = Flask(__name__)


@app.get("/")
def home():
    matchday = (request.args.get("matchday", "") or "").strip()
    date_value = (request.args.get("date", "") or "").strip()
    odds_file = (request.args.get("odds_file", "") or "").strip()
    action = (request.args.getlist("action")[-1] if request.args.getlist("action") else "refresh").strip().lower()
    tab = (request.args.get("tab", "futurs") or "futurs").strip().lower()
    no_auto = (request.args.get("no_auto", "") or "") in ("1", "on", "true")

    rows = []
    applied_results = 0
    error = ""
    recommendations = None

    try:
        fixtures = data.load_fixtures()
        ratings = data.load_ratings()
        if not no_auto:
            ratings, applied_results = updater.apply_completed_results(ratings, fixtures)

        selected = ui._select_fixtures(fixtures, date_value, matchday)
        if not selected:
            if date_value:
                error = f"Aucun match trouve pour la date {date_value}."
            else:
                error = f"Aucun match trouve pour la journee {matchday}."

        odds_board = ui._load_odds_board(odds_file)
        rows = ui._analyse_rows(selected, ratings, odds_board)
        if action == "reco":
            recommendations = ui._build_recommendations(rows)
    except Exception as exc:
        error = str(exc)

    body = ui._render_page(
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
    return Response(body, mimetype="text/html; charset=utf-8")


@app.get("/<path:_rest>")
def fallback(_rest: str):
    return home()


# Vercel entrypoint
handler = app
