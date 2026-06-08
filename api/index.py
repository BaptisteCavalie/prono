from pathlib import Path
import sys

from flask import Flask, Response, request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import autonomous, data, data_quality, odds_fetch, solidity, team_signals, updater
import ui

app = Flask(__name__)


@app.get("/")
def home():
    matchday = (request.args.get("matchday", "") or "").strip()
    date_value = (request.args.get("date", "") or "").strip()
    odds_file = (request.args.get("odds_file", "") or "").strip()
    action = (request.args.getlist("action")[-1] if request.args.getlist("action") else "refresh").strip().lower()
    tab = (request.args.get("tab", "futurs") or "futurs").strip().lower()
    if action == "reco":          # back-compat: old reco button -> Paris page
        tab = "paris"
    no_auto = (request.args.get("no_auto", "") or "") in ("1", "on", "true")
    try:
        bankroll = float((request.args.get("bankroll", "50") or "50").strip())
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
        try:
            autonomous.autonomous_refresh()
        except Exception:
            pass  # best-effort refresh; never block page rendering on it
        fixtures = data.load_fixtures()
        base_ratings = data.load_ratings()
        ratings = data.load_ratings()
        team_status = data.load_team_status()
        solidity_report = solidity.assess_model_solidity(fixtures, base_ratings)
        if not no_auto:
            ratings, applied_results = updater.apply_completed_results(ratings, fixtures)
        ratings = team_signals.adjust_ratings_with_status(ratings, team_status)
        health = data_quality.assess_data_health(fixtures, ratings, team_status)
        data_info = ui._build_data_info(fixtures, ratings, team_status, health, odds_file)

        selected = ui._select_fixtures(fixtures, date_value, matchday)
        if not selected:
            if date_value:
                error = f"Aucun match trouve pour la date {date_value}."
            else:
                error = f"Aucun match trouve pour la journee {matchday}."

        if odds_file:                                  # manual override (advanced)
            odds_board = ui._load_odds_board(odds_file)
        elif tab == "paris":                           # betting page: auto-fetch (cooldown + credit-capped)
            odds_board = odds_fetch.ensure_board(ratings, fixtures)
        else:                                          # other tabs: read cache only, never spend credits
            odds_board = odds_fetch.load_cached_board()
        rows = ui._analyse_rows(selected, ratings, odds_board, team_status=team_status)
        if tab == "paris":
            if (health or {}).get("level") == "critical":
                error = "Recommandations indisponibles: la qualite des donnees est critique. Mettez a jour fixtures, ratings et team_status puis reessayez."
            else:
                recommendations = ui._build_recommendations(rows, bankroll=bankroll)
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
        health,
        solidity_report,
        data_info,
        bankroll,
    )
    return Response(body, mimetype="text/html; charset=utf-8")


@app.get("/<path:_rest>")
def fallback(_rest: str):
    return home()


# Vercel entrypoint
handler = app
