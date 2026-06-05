# WC 2026 Prediction Engine

A local, dependency-free tool that predicts World Cup 2026 matches with an
Elo-driven Poisson model, and hands the close calls to Claude for live
injury/lineup/news analysis.

## Run

No install needed — system Python 3.9+ only (pure stdlib).

```bash
python3 predict.py --match "France vs Senegal"   # any two teams (also what-if / knockout)
python3 predict.py --group I                      # a whole group
python3 predict.py --matchday 1                   # every matchday-1 game
python3 predict.py --matchday 1 --loop           # ranked confidence + value + Claude queue
python3 predict.py --all --brief                  # all 72 group games + Claude handoff
python3 predict.py --list                         # show the groups
```

## What it outputs (per match)
- 1X2 probabilities, expected goals (xG) per side
- most likely scorelines
- Over/Under 2.5 and Both-Teams-To-Score
- a confidence level (never "high" when a rating is an estimate)
- with `--brief`: a structured **ASK CLAUDE** handoff listing what to research live

## How it works
1. `data/ratings.json` — each team's strength (World Football Elo).
   `source: live` = real Elo; `source: estimate` = approximation to refresh.
2. `engine/model.py` — Elo difference → expected goals (bounded logistic) →
   Poisson scoreline matrix → all the probabilities. Constants at the top are
   tunable for calibration.
3. `engine/report.py` — renders the card and the Claude brief.

## Data files
| File | What | How to refresh |
|------|------|----------------|
| `data/groups.json` | the 12 groups (final draw) | edit by hand or ask Claude |
| `data/ratings.json` | team Elo ratings | **ask Claude** to update with live numbers |
| `data/fixtures.json` | 72 group matches (generated) | `python3 tools/build_fixtures.py` |

The tool itself never touches the network — that keeps it robust and offline.
Live data refresh is done through Claude (the "ask Claude" layer), which has
working web access.

## Betting edges

```bash
# value: pass the bookmaker's 1X2 decimal odds, get de-vigged fair prices + EV
python3 predict.py --match "France vs Senegal" --odds "1.40,4.50,7.50"

# CLV tracker: prove you're beating the market over time
python3 track.py add --match "France vs Senegal" --sel France --odds 2.70 --stake 1
python3 track.py close --id 1 --closing 2.45     # CLV +10.2%
python3 track.py report

# loop value flags for a full matchday with manual prices
python3 predict.py --matchday 1 --loop --odds-file data/odds_md1.json
```

`--odds-file` expects JSON mapping either fixture IDs or match labels to decimal
1X2 triples:

```json
{
  "G01": [1.39, 4.50, 8.00],
  "Mexico vs South Africa": [1.39, 4.50, 8.00]
}
```

- **`engine/strategies.py`** surfaces documented historical leans: group-stage
  draws underpriced, knockout unders 2.5, host-nation overperformance.
- **`engine/odds.py`** removes the bookmaker margin and flags where the model's
  probability beats the fair price (positive EV).
- **`track.py`** logs your bets vs the closing line. Sustained **positive CLV**
  is the best evidence your edge is real (research is unanimous on this).

**Read this before betting a VALUE flag:** a flag means *the model disagrees
with the market* — and the market is usually right (it already prices in
injuries, lineups, news the model can't see). So treat every VALUE flag as a
**candidate to investigate**, not a bet. That's exactly what the "ask Claude"
layer is for: run the flagged match through Claude for live research before
staking. Blindly betting model-vs-market disagreements will lose.

> Outright-market note: history says **fade the shortest tournament favorite**
> (won only once in the last six WCs) and prefer mid-priced contenders.

## Honest limits
- Predictions are **probabilistic, not exact** — football is high variance.
- 29 of 48 teams currently use **estimated** ratings; ask Claude to refresh
  `ratings.json` with live Elo before relying on those matches.
- No automated odds feed (free, no keys) → pass odds yourself with `--odds`.
  The model is **calibrated to the market** (validated on Brazil–Morocco: model
  61/24/15 vs market 59/23/18), but favourites at very large rating gaps may run
  a touch high — sanity-check big mismatches against the price.
- Group matches are modelled at a **neutral venue** (host advantage off by
  default).

## Roadmap
- **Day 1 (done):** fixtures + ratings + Poisson model + CLI cards ✅
- **Day 3 (done early):** odds → de-vig → value flags, WC strategy leans, CLV tracker ✅
- **Day 4 (done early):** calibration — Dixon-Coles draw correction + goals-scale fix, validated vs market ✅
- **Day 2:** richer report (HTML), full-matchday view
- **Next:** refresh the 29 estimate ratings; real dates/venues; knockout bracket
