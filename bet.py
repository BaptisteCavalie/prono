#!/usr/bin/env python3
"""Safe betting planner — turns the model + your market odds into a sized plan.

It only ever recommends *value* (model edge over the de-vigged price), shrinks the
model toward the market to tame its overconfidence, sizes with quarter-Kelly under
hard caps, and treats combos as a tiny, ring-fenced extra. Built on the WC2022
backtest findings (tools/backtest_wc2022*).

Examples:
  python bet.py --matchday 1 --odds-file data/odds_md1.json --bankroll 200
  python bet.py --date 2026-06-12 --odds-file odds.json --combos
  python bet.py --match "France vs Senegal" --odds "1.40,4.50,7.50" --bankroll 100
"""
import argparse
import json
import sys

from engine import betting, data
from predict import _analyse_match, _find_match_odds, _load_odds_board, _parse_date, _split_match


def _label(home, away):
    return f"{home} vs {away}"


def _sel_text(sel, home, away):
    return {"home": f"{home} win", "draw": "Draw", "away": f"{away} win"}[sel]


def _evaluate_fixtures(ratings, fixtures, board, market_weight, kelly):
    evals = []
    for m in fixtures:
        odds = _find_match_odds(m, board)
        home, away, rh, ra, out = _analyse_match(ratings, m)
        bet = None
        if odds:
            bet = betting.evaluate_single(out, tuple(odds), market_weight, kelly)
        evals.append({
            "key": str(m.get("id", "")) or _label(home, away),
            "label": _label(home, away),
            "home": home, "away": away,
            "has_odds": bool(odds), "bet": bet,
        })
    return evals


def _print_plan(staked, combos, bankroll, evals, want_combos):
    print("SINGLES (value only)")
    print("-" * 72)
    if not staked:
        print("  no value bets — sit this slate out (this is the common case)")
    for e in staked:
        b = e["bet"]
        sel = _sel_text(b["sel"], e["home"], e["away"])
        print(f"  {e['label']:<32} {sel:<14} @{b['odds']:.2f}")
        print(f"      model {b['model']*100:.0f}% -> shrunk {b['shrunk']*100:.0f}% "
              f"(fair {b['fair']*100:.0f}%)  edge +{b['edge']*100:.0f}pt  "
              f"EV {b['ev']*100:+.1f}%  ->  STAKE {e['stake']:.2f}")

    skipped = [e for e in evals if e["has_odds"] and not e["bet"]]
    if skipped:
        print("\n  no value (priced fairly): "
              + ", ".join(e["label"] for e in skipped[:8])
              + (" ..." if len(skipped) > 8 else ""))
    no_odds = [e for e in evals if not e["has_odds"]]
    if no_odds:
        print(f"  no odds provided for {len(no_odds)} fixture(s)")

    if want_combos:
        print("\nCOMBOS (max 2 legs · ring-fenced ≤5% of bankroll · entertainment only)")
        print("-" * 72)
        if not combos:
            print("  none survive the margin on shrunk probs — skip combos")
        for c in combos:
            legs = " + ".join(f"{l['label']} ({_sel_text(l['sel'], '', '').strip() or l['sel']})"
                              f" @{l['odds']:.2f}" for l in c["legs"])
            print(f"  {legs}")
            print(f"      = {c['combined_odds']:.2f}  EV {c['ev']*100:+.1f}%  "
                  f"->  STAKE {c['stake']:.2f}")

    single_stake = sum(e["stake"] for e in staked)
    combo_stake = sum(c["stake"] for c in combos)
    ev_profit = (sum(e["stake"] * e["bet"]["ev"] for e in staked)
                 + sum(c["stake"] * c["ev"] for c in combos))
    print("\nEXPOSURE")
    print("-" * 72)
    print(f"  singles staked : {single_stake:7.2f}  ({single_stake/bankroll*100:.1f}% of bankroll)")
    if want_combos:
        print(f"  combos staked  : {combo_stake:7.2f}  ({combo_stake/bankroll*100:.1f}% of bankroll)")
    print(f"  total at risk  : {single_stake + combo_stake:7.2f}")
    print(f"  expected profit: {ev_profit:+7.2f}  (model-EV; trust it only as far as the model is calibrated)")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Safe betting planner")
    p.add_argument("--match", help='single match: "Home vs Away" (needs --odds)')
    p.add_argument("--odds", help='1X2 decimals for --match, e.g. "1.40,4.50,7.50"')
    p.add_argument("--odds-file", help="JSON: fixture id or 'Home vs Away' -> [home,draw,away]")
    p.add_argument("--group")
    p.add_argument("--matchday", type=int, choices=[1, 2, 3])
    p.add_argument("--date", help="fixture date YYYY-MM-DD")
    p.add_argument("--all", action="store_true")
    p.add_argument("--bankroll", type=float, default=100.0)
    p.add_argument("--market-weight", type=float, default=betting.MARKET_WEIGHT,
                   help="0=trust model, 1=copy market (default %(default)s, leans safe)")
    p.add_argument("--kelly", type=float, default=betting.KELLY_FRACTION,
                   help="Kelly fraction (default %(default)s = quarter-Kelly)")
    p.add_argument("--combos", action="store_true", help="also propose ≤2-leg combos")
    args = p.parse_args(argv)

    if args.bankroll <= 0:
        print("--bankroll must be > 0", file=sys.stderr)
        return 2

    ratings = data.load_ratings()

    if args.match:
        pair = _split_match(args.match)
        if not pair or not args.odds:
            print('Use: --match "Home vs Away" --odds "h,d,a"', file=sys.stderr)
            return 2
        home = data.resolve_team(pair[0], ratings)
        away = data.resolve_team(pair[1], ratings)
        if not (home and away):
            print("Unknown team in --match", file=sys.stderr)
            return 2
        try:
            triple = [float(x) for x in args.odds.split(",")]
            assert len(triple) == 3
        except (ValueError, AssertionError):
            print('--odds needs 3 decimals "home,draw,away"', file=sys.stderr)
            return 2
        m = {"home": home, "away": away, "home_adv": 0.0}
        evals = _evaluate_fixtures(ratings, [m], {f"{home.lower()}|{away.lower()}": triple},
                                   args.market_weight, args.kelly)
        staked = betting.plan_singles(evals, args.bankroll)
        combos = betting.build_combos(staked, args.bankroll) if args.combos else []
        print(f"SAFE BETTING PLAN · {home} vs {away} · bankroll {args.bankroll:.2f}")
        print("=" * 72)
        _print_plan(staked, combos, args.bankroll, evals, args.combos)
        return 0

    if not args.odds_file:
        print("Provide --odds-file for a slate (or --match/--odds for one game)", file=sys.stderr)
        return 2
    if not (args.group or args.matchday or args.date or args.all):
        print("Pick a slate: --matchday / --date / --group / --all", file=sys.stderr)
        return 2

    try:
        board = _load_odds_board(args.odds_file)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        print(f"Unable to load --odds-file: {e}", file=sys.stderr)
        return 2

    fixtures = data.load_fixtures()
    sel = fixtures
    if args.date:
        try:
            target = _parse_date(args.date)
        except ValueError:
            print("--date must be YYYY-MM-DD", file=sys.stderr)
            return 2
        sel = [m for m in sel if m.get("date") and _parse_date(m["date"]) == target]
    if args.group:
        sel = [m for m in sel if m["group"].upper() == args.group.upper()]
    if args.matchday:
        sel = [m for m in sel if m["matchday"] == args.matchday]
    if not sel:
        print("No fixtures match that selection", file=sys.stderr)
        return 2

    evals = _evaluate_fixtures(ratings, sel, board, args.market_weight, args.kelly)
    staked = betting.plan_singles(evals, args.bankroll)
    combos = betting.build_combos(staked, args.bankroll) if args.combos else []

    tag = args.date or (f"MD{args.matchday}" if args.matchday else
                        (f"Group {args.group}" if args.group else "all fixtures"))
    print(f"SAFE BETTING PLAN · {tag} · bankroll {args.bankroll:.2f}")
    print("=" * 72)
    print(f"market weight {args.market_weight:.2f} (model shrunk toward market) · "
          f"{args.kelly:g}-Kelly · cap {betting.MAX_STAKE_FRAC*100:.0f}%/bet, "
          f"{betting.SLATE_EXPOSURE_CAP*100:.0f}%/slate\n")
    _print_plan(staked, combos, args.bankroll, evals, args.combos)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
