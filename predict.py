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

from engine import data, model, report, strategies
from engine import odds as oddsmod


def _split_match(s: str):
    for sep in (" vs ", " VS ", " v ", "/", " - "):
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return None


def _emit(ratings, home, away, match, show_brief, odds=None, simple=False):
    rh = ratings["teams"][home]
    ra = ratings["teams"][away]
    out = model.analyse(rh["rating"], ra["rating"], home_adv=match.get("home_adv", 0.0))
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


def _loop(ratings, fixtures, odds_board):
    rows = []
    for m in fixtures:
        home, away = m["home"], m["away"]
        rh = ratings["teams"][home]
        ra = ratings["teams"][away]
        out = model.analyse(rh["rating"], ra["rating"], home_adv=m.get("home_adv", 0.0))
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
        })

    ranked = sorted(rows, key=lambda r: (-r["pick_prob"], -r["out"]["top_scores"][0][1]))
    review_queue = [r for r in sorted(rows, key=lambda r: (-r["review_priority"], r["pick_prob"]))
                    if r["review_reasons"]]

    md = fixtures[0].get("matchday") if fixtures else "?"
    print(f"MATCHDAY LOOP · MD{md}")
    print("=" * 64)
    print("Ranked by confidence")
    for idx, r in enumerate(ranked, start=1):
        (i, j), sp = r["out"]["top_scores"][0]
        est_tag = "*" if r["est"] else ""
        vtag = " VALUE" if r["values"] else ""
        print(
            f"{idx:>2}. {r['home']} vs {r['away']:<26} "
            f"pick {r['pick']} {round(r['pick_prob'] * 100):>2}%{est_tag} "
            f"score {i}-{j} {round(sp * 100):>2}%{est_tag} "
            f"conf {r['conf']}{vtag}"
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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="WC2026 prediction engine")
    p.add_argument("--match", help='two teams, e.g. "France vs Senegal"')
    p.add_argument("--group", help="group letter A-L")
    p.add_argument("--matchday", type=int, choices=[1, 2, 3])
    p.add_argument("--all", action="store_true", help="all group fixtures")
    p.add_argument("--brief", action="store_true", help="add Claude handoff brief")
    p.add_argument("--loop", action="store_true",
                   help="matchday loop: ranked confidence + value flags + Claude queue")
    p.add_argument("--simple", action="store_true",
                   help="terse output: exact score + bet, each with confidence %")
    p.add_argument("--odds", help='market 1X2 decimal odds for --match, e.g. "1.40,4.50,7.50"')
    p.add_argument("--odds-file",
                   help="JSON mapping fixture id (e.g. G01) or 'Home vs Away' to [home,draw,away]")
    p.add_argument("--list", action="store_true", help="list groups")
    args = p.parse_args(argv)

    ratings = data.load_ratings()

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

    if not (args.group or args.matchday or args.all):
        p.print_help()
        return 0

    sel = data.load_fixtures()
    if args.group:
        sel = [m for m in sel if m["group"].upper() == args.group.upper()]
    if args.matchday:
        sel = [m for m in sel if m["matchday"] == args.matchday]
    if args.loop:
        if not args.matchday:
            print("--loop currently requires --matchday (real calendar dates not loaded yet)",
                  file=sys.stderr)
            return 2
        try:
            odds_board = _load_odds_board(args.odds_file)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            print(f"Unable to load --odds-file: {e}", file=sys.stderr)
            return 2
        _loop(ratings, sel, odds_board)
        return 0
    for m in sel:
        _emit(ratings, m["home"], m["away"], m, args.brief, simple=args.simple)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
