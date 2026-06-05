#!/usr/bin/env python3
"""Bet log + Closing Line Value (CLV) tracker.

CLV is the best evidence you are betting +EV: if the odds you took are
consistently better than the closing odds, you are beating the market.

Usage:
  python3 track.py add --match "France vs Senegal" --sel France --odds 2.70 --stake 1
  python3 track.py close --id 1 --closing 2.45
  python3 track.py report
  python3 track.py list
"""
import argparse
import json
from pathlib import Path

BETS = Path(__file__).resolve().parent / "data" / "bets.json"


def _load():
    if BETS.exists():
        return json.loads(BETS.read_text(encoding="utf-8"))
    return {"bets": []}


def _save(d):
    BETS.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _clv(odds_taken, closing):
    # In decimal odds, higher is better, so taking longer odds than close = +CLV.
    return (odds_taken / closing - 1.0) * 100.0


def add(a):
    d = _load()
    bet = {"id": (max([b["id"] for b in d["bets"]], default=0) + 1),
           "match": a.match, "sel": a.sel, "odds": a.odds,
           "stake": a.stake, "closing": None}
    d["bets"].append(bet)
    _save(d)
    print(f"logged #{bet['id']}: {a.match} | {a.sel} @ {a.odds} (stake {a.stake})")


def close(a):
    d = _load()
    for b in d["bets"]:
        if b["id"] == a.id:
            b["closing"] = a.closing
            _save(d)
            print(f"#{a.id} closing {a.closing} -> CLV {_clv(b['odds'], a.closing):+.1f}%")
            return
    print(f"no bet with id {a.id}")


def list_(a):
    d = _load()
    if not d["bets"]:
        print("no bets logged")
        return
    for b in d["bets"]:
        clv = f"{_clv(b['odds'], b['closing']):+.1f}%" if b["closing"] else "open"
        print(f"#{b['id']:>3}  {b['match']:<28} {b['sel']:<12} "
              f"@{b['odds']:.2f}  close {b['closing'] or '-'}  CLV {clv}")


def report(a):
    d = _load()
    closed = [b for b in d["bets"] if b["closing"]]
    if not closed:
        print("no closed bets yet — add closing odds with `close --id N --closing X`")
        return
    clvs = [_clv(b["odds"], b["closing"]) for b in closed]
    avg = sum(clvs) / len(clvs)
    beat = sum(1 for c in clvs if c > 0)
    print(f"closed bets: {len(closed)}")
    print(f"average CLV: {avg:+.2f}%")
    print(f"beat the close: {beat}/{len(closed)} ({round(100 * beat / len(closed))}%)")
    print("positive CLV sustained over many bets ~ long-term +EV. It is the "
          "single best signal that your edge is real.")


def main(argv=None):
    p = argparse.ArgumentParser(description="bet log + CLV tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("add", help="log a bet")
    pa.add_argument("--match", required=True)
    pa.add_argument("--sel", required=True, help="selection, e.g. team name / Over2.5")
    pa.add_argument("--odds", type=float, required=True, help="decimal odds you took")
    pa.add_argument("--stake", type=float, default=1.0)
    pa.set_defaults(func=add)

    pc = sub.add_parser("close", help="record the closing odds for a bet")
    pc.add_argument("--id", type=int, required=True)
    pc.add_argument("--closing", type=float, required=True)
    pc.set_defaults(func=close)

    sub.add_parser("list", help="list all bets").set_defaults(func=list_)
    sub.add_parser("report", help="CLV summary").set_defaults(func=report)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
