#!/usr/bin/env python3
"""World Cup 2026 prediction engine — CLI.

Examples:
  python predict.py --match "France vs Senegal"   # any two teams (also knockout/what-if)
  python predict.py --group I                      # one group
  python predict.py --matchday 1                   # all matchday-1 games
  python predict.py --all --brief                  # everything + Claude handoff
  python predict.py --list                         # show groups
"""
import argparse
import json
import sys
from datetime import datetime
from typing import Dict

from engine import autonomous, data, data_quality, model, mpp, report, solidity, strategies, team_signals
from engine import odds as oddsmod
from engine import updater


def _split_match(s: str):
    for sep in (" vs ", " VS ", " v ", "/", " - "):
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return None


def _emit(ratings, home, away, match, show_brief, odds=None, simple=False):
    rh = ratings["teams"][home]
    ra = ratings["teams"][away]
    out = model.analyse(rh["rating"], ra["rating"], home_adv=match.get("home_adv", 0.0),
                        ad_home=model.ad_from_row(rh), ad_away=model.ad_from_row(ra))
    if simple:
        rows = oddsmod.value_1x2(out, odds[0], odds[1], odds[2]) if odds else None
        print(report.simple(match, home, away, rh, ra, out, rows))
        return
    print(report.card(match, home, away, rh, ra, out))
    leans = strategies.flags(match, home, away, rh, ra, out)
    if leans:
        print(report.render_flags(leans))
    if odds:
        rows = oddsmod.value_1x2(out, odds[0], odds[1], odds[2])
        print(report.render_value(home, away, rows))
    if show_brief:
        print()
        print(report.brief(match, home, away, rh, ra, out))


def _match_key(match):
    return f"{match['home'].lower()}|{match['away'].lower()}"


def _load_odds_board(path):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    board = {}
    for key, triple in raw.items():
        if (not isinstance(triple, list) or len(triple) != 3
                or not all(isinstance(x, (int, float)) for x in triple)):
            raise ValueError(
                f"invalid odds for {key!r}; expected [home, draw, away] decimals")
        if key.lower().startswith("g"):
            board[key.upper()] = [float(x) for x in triple]
            continue
        pair = _split_match(key)
        if pair:
            board[f"{pair[0].strip().lower()}|{pair[1].strip().lower()}"] = [float(x) for x in triple]
            continue
        raise ValueError(
            f"invalid key {key!r}; use fixture id like 'G01' or 'Home vs Away'")
    return board


def _find_match_odds(match, board):
    if not board:
        return None
    return board.get(str(match.get("id", "")).upper()) or board.get(_match_key(match))


def _parse_date(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _analyse_match(ratings, match):
    home, away = match["home"], match["away"]
    rh = ratings["teams"][home]
    ra = ratings["teams"][away]
    out = model.analyse(rh["rating"], ra["rating"], home_adv=match.get("home_adv", 0.0),
                        ad_home=model.ad_from_row(rh), ad_away=model.ad_from_row(ra))
    return home, away, rh, ra, out


def _sheet(ratings, fixtures, odds_board):
    md = fixtures[0].get("matchday") if fixtures else "?"
    date_value = fixtures[0].get("date") if fixtures and fixtures[0].get("date") else None
    tag = date_value[:10] if date_value else f"MD{md}"
    print(f"DAILY SHEET · {tag}")
    print("=" * 64)
    for match in fixtures:
        home, away, rh, ra, out = _analyse_match(ratings, match)
        odds = _find_match_odds(match, odds_board)
        rows = oddsmod.value_1x2(out, odds[0], odds[1], odds[2]) if odds else None
        print(report.simple(match, home, away, rh, ra, out, rows))
        print()


def _loop(ratings, fixtures, odds_board, min_pick_prob=0.0, review_top=0):
    rows = []
    for m in fixtures:
        home, away, rh, ra, out = _analyse_match(ratings, m)
        pick_name, pick_prob = max(
            ((home, out["p_home"]), ("Draw", out["p_draw"]), (away, out["p_away"])),
            key=lambda kv: kv[1],
        )
        conf = report.confidence(out, rh.get("source") == "live" and ra.get("source") == "live")
        est = rh.get("source") != "live" or ra.get("source") != "live"
        leans = strategies.flags(m, home, away, rh, ra, out)
        odds = _find_match_odds(m, odds_board)
        value_rows = oddsmod.value_1x2(out, odds[0], odds[1], odds[2]) if odds else []
        values = [r for r in value_rows if r["value"]]

        review_reasons = []
        if values:
            review_reasons.append("market disagreement")
        if est:
            review_reasons.append("estimated rating involved")
        if pick_prob < 0.50:
            review_reasons.append("close 1X2")
        if leans:
            review_reasons.append("historical angle")

        review_priority = 0
        review_priority += 3 if values else 0
        review_priority += 2 if est else 0
        review_priority += 1 if pick_prob < 0.50 else 0
        review_priority += 1 if leans else 0

        rows.append({
            "match": m,
            "home": home,
            "away": away,
            "out": out,
            "pick": pick_name,
            "pick_prob": pick_prob,
            "conf": conf,
            "est": est,
            "leans": leans,
            "values": values,
            "review_reasons": review_reasons,
            "review_priority": review_priority,
            "rec": mpp.recommend(out, odds),
        })

    ranked = sorted(rows, key=lambda r: (-r["pick_prob"], -r["out"]["top_scores"][0][1]))
    if min_pick_prob > 0.0:
        ranked = [r for r in ranked if r["pick_prob"] >= min_pick_prob]
    review_queue = [r for r in sorted(rows, key=lambda r: (-r["review_priority"], r["pick_prob"]))
                    if r["review_reasons"]]
    if review_top and review_top > 0:
        review_queue = review_queue[:review_top]

    md = fixtures[0].get("matchday") if fixtures else "?"
    print(f"MATCHDAY LOOP · MD{md}")
    print("=" * 64)
    print("Ranked by confidence")
    if not ranked:
        print(" - no matches after filtering")
    for idx, r in enumerate(ranked, start=1):
        rec = r["rec"]
        i, j = rec["score"]
        est_tag = "*" if r["est"] else ""
        vtag = " VALUE" if r["values"] else ""
        print(
            f"{idx:>2}. {r['home']} vs {r['away']:<26} "
            f"pick {r['pick']} {round(r['pick_prob'] * 100):>2}%{est_tag} "
            f"prono {i}-{j} +{rec['bonus']:>3} {rec['tier']:<9} "
            f"E[MPP] {rec['exp_points']:>4.1f} "
            f"conf {r['conf']}{vtag}"
        )

    print()
    print("MPP X2 boost candidate (highest expected points)")
    x2 = max(rows, key=lambda r: r["rec"]["exp_points"])
    xr = x2["rec"]
    xi, xj = xr["score"]
    print(
        f" - {x2['home']} vs {x2['away']}: {xi}-{xj} "
        f"(+{xr['bonus']} {xr['tier']}, E[MPP] {xr['exp_points']:.1f}) "
        f"-> double it with your one X2"
    )

    print()
    print("Value flags")
    if not odds_board:
        print(" - none (no --odds-file provided)")
    else:
        found = 0
        for r in ranked:
            for v in r["values"]:
                label = {"home": f"{r['home']} win", "draw": "Draw", "away": f"{r['away']} win"}[v["sel"]]
                print(
                    f" - {r['home']} vs {r['away']}: {label} @ {v['odds']:.2f} "
                    f"(model {round(v['model'] * 100)}%, EV {v['ev'] * 100:+.1f}%)"
                )
                found += 1
        if found == 0:
            print(" - none (no positive-EV edges vs provided prices)")

    print()
    print("Claude review queue")
    if not review_queue:
        print(" - none")
    for idx, r in enumerate(review_queue, start=1):
        reasons = ", ".join(r["review_reasons"])
        print(
            f" {idx:>2}. {r['home']} vs {r['away']} "
            f"(priority {r['review_priority']}) -> {reasons}"
        )


def _print_solidity_report(solidity_report: Dict, title: str = "MODEL SOLIDITY") -> None:
    print(title)
    print("=" * 64)
    if solidity_report.get("score") is None:
        print("score: n/a (insufficient)")
    else:
        print(f"score: {solidity_report['score']}/100 ({solidity_report['level']})")
    print(f"matches evaluated: {solidity_report['matches']}")
    if solidity_report.get("result_accuracy") is not None:
        print(f"1X2 accuracy: {round(solidity_report['result_accuracy'] * 100)}%")
    if solidity_report.get("exact_score_hit") is not None:
        print(f"exact score hit: {round(solidity_report['exact_score_hit'] * 100)}%")
    if solidity_report.get("brier_1x2") is not None:
        print(f"1X2 brier: {solidity_report['brier_1x2']:.3f}")
    if solidity_report.get("logloss_1x2") is not None:
        print(f"1X2 log-loss: {solidity_report['logloss_1x2']:.3f}")
    if solidity_report.get("rps_1x2") is not None:
        print(f"1X2 RPS (lower=better): {solidity_report['rps_1x2']:.3f}")
    if solidity_report.get("avg_pick_conf") is not None:
        print(f"avg pick confidence: {round(solidity_report['avg_pick_conf'] * 100)}%")
    if solidity_report.get("calibration_gap") is not None:
        gap = solidity_report["calibration_gap"] * 100
        print(f"calibration gap (conf-hit): {gap:+.1f}pt")

    buckets = solidity_report.get("confidence_buckets") or []
    if buckets:
        print("confidence buckets:")
        for b in buckets:
            print(
                f" - {b['range']}: n={b['count']} hit={round(b['hit_rate'] * 100)}% "
                f"conf={round(b['avg_conf'] * 100)}% gap={(b['gap'] * 100):+.1f}pt"
            )

    if solidity_report.get("alerts"):
        print("alerts:")
        for a in solidity_report["alerts"]:
            print(f" - {a}")
    print()


def _fmt_pct(value):
    if value is None:
        return "n/a"
    return f"{round(value * 100)}%"


def _print_coverage_report(health: Dict, fixture_count: int) -> None:
    print("MISSING DATA COVERAGE")
    print("=" * 64)
    print(
        "ratings live coverage: "
        f"{(health.get('ratings_total_teams') or 0) - (health.get('ratings_estimate_count') or 0)}"
        f"/{health.get('ratings_total_teams') or 0} "
        f"({_fmt_pct(1.0 - (health.get('ratings_estimate_pct') or 0.0) if health.get('ratings_total_teams') else None)})"
    )
    print(
        "team status coverage: "
        f"{(health.get('status_total_teams') or 0) - (health.get('status_missing_count') or 0)}"
        f"/{health.get('status_total_teams') or 0} "
        f"({_fmt_pct(health.get('status_coverage_pct'))})"
    )
    print(
        "home_adv coverage: "
        f"{health.get('fixtures_with_home_adv') or 0}/{fixture_count} "
        f"({_fmt_pct(health.get('home_adv_coverage_pct'))})"
    )
    if health.get("status_missing_sample"):
        print("missing team_status sample:")
        for team in health["status_missing_sample"]:
            print(f" - {team}")
    print()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="WC2026 prediction engine")
    p.add_argument("--match", help='two teams, e.g. "France vs Senegal"')
    p.add_argument("--group", help="group letter A-L")
    p.add_argument("--matchday", type=int, choices=[1, 2, 3])
    p.add_argument("--date", help="fixture date (YYYY-MM-DD) for date-based loop selection")
    p.add_argument("--all", action="store_true", help="all group fixtures")
    p.add_argument("--brief", action="store_true", help="add Claude handoff brief")
    p.add_argument("--sheet", action="store_true",
                   help="daily one-page card: exact score + bet recommendation for each game")
    p.add_argument("--loop", action="store_true",
                   help="matchday loop: ranked confidence + value flags + Claude queue")
    p.add_argument("--simple", action="store_true",
                   help="terse output: exact score + bet, each with confidence pct")
    p.add_argument("--odds", help='market 1X2 decimal odds for --match, e.g. "1.40,4.50,7.50"')
    p.add_argument("--odds-file",
                   help="JSON mapping fixture id (e.g. G01) or 'Home vs Away' to [home,draw,away]")
    p.add_argument("--review-top", type=int, default=0,
                   help="limit Claude review queue to top N items (0 = all)")
    p.add_argument("--min-pick-prob", type=float, default=0.0,
                   help="hide ranked picks below this probability (0.0-1.0)")
    p.add_argument("--no-auto-update", action="store_true",
                   help="disable automatic rating updates from completed fixtures")
    p.add_argument("--no-auto-refresh", action="store_true",
                   help="disable autonomous data refresh (live ratings/home_adv/prediction snapshots)")
    p.add_argument("--auto-refresh-force", action="store_true",
                   help="force autonomous refresh now (ignores cooldown)")
    p.add_argument("--health-report", action="store_true",
                   help="print data freshness/quality report before predictions")
    p.add_argument("--coverage-report", action="store_true",
                   help="print what data is missing (ratings/team status/home_adv coverage)")
    p.add_argument("--backtest", action="store_true",
                   help="run detailed backtest/calibration report on completed matches")
    p.add_argument("--backtest-last", type=int, default=0,
                   help="restrict backtest to the last N completed matches (0 = all)")
    p.add_argument("--list", action="store_true", help="list groups")
    args = p.parse_args(argv)

    auto_report = None
    if not args.no_auto_refresh:
        auto_report = autonomous.autonomous_refresh(force=args.auto_refresh_force)

    ratings = data.load_ratings()
    fixtures = data.load_fixtures()
    team_status = data.load_team_status()
    solidity_report = solidity.assess_model_solidity(fixtures, ratings)

    if args.backtest_last < 0:
        print("--backtest-last must be >= 0", file=sys.stderr)
        return 2

    if args.backtest:
        completed = [m for m in fixtures if m.get("actual_home") is not None and m.get("actual_away") is not None]
        if args.backtest_last > 0 and len(completed) > args.backtest_last:
            completed = sorted(completed, key=lambda m: (str(m.get("date") or "9999-99-99"), m.get("id") or ""))[-args.backtest_last:]
        backtest_report = solidity.assess_model_solidity(completed, ratings)
        _print_solidity_report(backtest_report, title="MODEL BACKTEST")
        return 0

    applied_results = 0
    if not args.no_auto_update:
        ratings, applied_results = updater.apply_completed_results(ratings, fixtures)
    ratings = team_signals.adjust_ratings_with_status(ratings, team_status)
    health = data_quality.assess_data_health(fixtures, ratings, team_status)

    if args.health_report:
        if auto_report and auto_report.get("ran"):
            print("AUTONOMOUS REFRESH")
            print("=" * 64)
            print(
                "ratings matched/updated: "
                f"{auto_report.get('ratings_matched', 0)}/{auto_report.get('ratings_updated', 0)}"
            )
            print(
                "home_adv rows updated: "
                f"{auto_report.get('home_adv_updated', 0)}"
            )
            print(
                "team_status rows added: "
                f"{auto_report.get('team_status_added', 0)}"
            )
            print(
                "prediction snapshots updated: "
                f"{auto_report.get('predictions_updated', 0)}"
            )
            if auto_report.get("errors"):
                print("refresh warnings:")
                for err in auto_report["errors"]:
                    print(f" - {err}")
            print()
        elif auto_report and auto_report.get("skipped"):
            print(f"AUTONOMOUS REFRESH: skipped ({auto_report.get('reason')})")
            print()

        print("DATA HEALTH")
        print("=" * 64)
        print(f"score: {health['score']}/100 ({health['level']})")
        print(f"missing fixture dates: {health['fixtures_missing_dates']}")
        print(f"past fixtures without final score: {health['fixtures_past_without_score']}")
        print(f"ratings age (days): {health['ratings_age_days']}")
        print(
            "estimated ratings: "
            f"{health.get('ratings_estimate_count', 0)}/{health.get('ratings_total_teams', 0)}"
            f" ({_fmt_pct(health.get('ratings_estimate_pct'))})"
        )
        print(f"team_status age (days): {health['status_age_days']}")
        print(
            "team_status coverage: "
            f"{(health.get('status_total_teams') or 0) - (health.get('status_missing_count') or 0)}"
            f"/{health.get('status_total_teams') or 0}"
            f" ({_fmt_pct(health.get('status_coverage_pct'))})"
        )
        print(
            "home_adv coverage: "
            f"{health.get('fixtures_with_home_adv', 0)}/{len(fixtures)}"
            f" ({_fmt_pct(health.get('home_adv_coverage_pct'))})"
        )
        if health["alerts"]:
            print("alerts:")
            for a in health["alerts"]:
                print(f" - {a}")
        print()

        _print_solidity_report(solidity_report)

    if args.coverage_report:
        _print_coverage_report(health, len(fixtures))

    if args.list:
        for g, teams in sorted(data.load_groups().items()):
            print(f"Group {g}: " + ", ".join(teams))
        return 0

    if args.match:
        pair = _split_match(args.match)
        if not pair:
            print('Use: --match "Home vs Away"', file=sys.stderr)
            return 2
        home = data.resolve_team(pair[0], ratings)
        away = data.resolve_team(pair[1], ratings)
        if not (home and away):
            miss = pair[0] if not home else pair[1]
            print(f"Unknown team: {miss!r}", file=sys.stderr)
            return 2
        odds = None
        if args.odds:
            try:
                odds = [float(x) for x in args.odds.split(",")]
                assert len(odds) == 3
            except (ValueError, AssertionError):
                print('--odds needs 3 decimals "home,draw,away"', file=sys.stderr)
                return 2
        _emit(ratings, home, away, {"venue": "neutral"}, args.brief, odds, args.simple)
        return 0

    if not (args.group or args.matchday or args.date or args.all):
        p.print_help()
        return 0

    if args.min_pick_prob < 0 or args.min_pick_prob > 1:
        print("--min-pick-prob must be between 0.0 and 1.0", file=sys.stderr)
        return 2
    if args.review_top < 0:
        print("--review-top must be >= 0", file=sys.stderr)
        return 2

    sel = fixtures
    if args.date:
        try:
            target_date = _parse_date(args.date)
        except ValueError:
            print("--date must be YYYY-MM-DD", file=sys.stderr)
            return 2
        sel = [m for m in sel if m.get("date") and _parse_date(m["date"]) == target_date]
        if not sel:
            print(f"No fixtures found for --date {args.date}", file=sys.stderr)
            return 2
    if args.group:
        sel = [m for m in sel if m["group"].upper() == args.group.upper()]
    if args.matchday:
        sel = [m for m in sel if m["matchday"] == args.matchday]
    if args.sheet:
        if not (args.matchday or args.date):
            print("--sheet requires --matchday or --date YYYY-MM-DD", file=sys.stderr)
            return 2
        try:
            odds_board = _load_odds_board(args.odds_file)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            print(f"Unable to load --odds-file: {e}", file=sys.stderr)
            return 2
        _sheet(ratings, sel, odds_board)
        if applied_results:
            print(f"Applied {applied_results} completed result(s) to ratings before prediction.")
        return 0
    if args.loop:
        if not (args.matchday or args.date):
            print("--loop requires --matchday or --date YYYY-MM-DD", file=sys.stderr)
            return 2
        try:
            odds_board = _load_odds_board(args.odds_file)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            print(f"Unable to load --odds-file: {e}", file=sys.stderr)
            return 2
        _loop(
            ratings,
            sel,
            odds_board,
            min_pick_prob=args.min_pick_prob,
            review_top=args.review_top,
        )
        if applied_results:
            print()
            print(f"Applied {applied_results} completed result(s) to ratings before prediction.")
        return 0
    for m in sel:
        _emit(ratings, m["home"], m["away"], m, args.brief, simple=args.simple)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
