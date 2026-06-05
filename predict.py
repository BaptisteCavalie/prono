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


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="WC2026 prediction engine")
    p.add_argument("--match", help='two teams, e.g. "France vs Senegal"')
    p.add_argument("--group", help="group letter A-L")
    p.add_argument("--matchday", type=int, choices=[1, 2, 3])
    p.add_argument("--all", action="store_true", help="all group fixtures")
    p.add_argument("--brief", action="store_true", help="add Claude handoff brief")
    p.add_argument("--simple", action="store_true",
                   help="terse output: exact score + bet, each with confidence %")
    p.add_argument("--odds", help='market 1X2 decimal odds for --match, e.g. "1.40,4.50,7.50"')
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
    for m in sel:
        _emit(ratings, m["home"], m["away"], m, args.brief, simple=args.simple)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
