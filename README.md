# WC 2026 Prediction Engine

A local, dependency-free tool that predicts World Cup 2026 matches with an
Elo-driven Poisson model, and hands the close calls to Claude for live
injury/lineup/news analysis.

## Run

No install needed — system Python 3.9+ only (pure stdlib).

```bash
python3 predict.py --match "France vs Senegal"   # any two teams (also what-if / knockout)
python3 predict.py --match "France vs Croatia" --knockout  # scored on the 120' result (MPP rule)
python3 predict.py --simulate                     # Monte-Carlo tournament: qualif/run/title prob per team
python3 predict.py --bracket                       # projected bracket (most-likely scenario) + x2 plan
python3 predict.py --outrights                     # value on long-term markets (data/outrights.json)
python3 predict.py --simulate --bracket --outrights --sims 30000  # everything, more precise
python3 predict.py --group I                      # a whole group
python3 predict.py --matchday 1                   # every matchday-1 game
python3 predict.py --matchday 1 --sheet          # one-page daily card (score + bet with %)
python3 predict.py --matchday 1 --loop           # ranked confidence + value + Claude queue
python3 predict.py --health-report --matchday 1  # data freshness/quality audit + predictions
python3 predict.py --coverage-report --matchday 1 # explicit missing-data coverage report
python3 predict.py --health-report --auto-refresh-force --matchday 1 # force autonomous data refresh now
python3 predict.py --backtest                    # full backtest + calibration on completed matches
python3 predict.py --backtest --backtest-last 20 # backtest limited to latest 20 completed matches
python3 predict.py --date 2026-06-11 --loop      # date-based loop once fixture dates exist
python3 predict.py --all --brief                  # all 72 group games + Claude handoff
python3 predict.py --list                         # show the groups
python3 ui.py                                     # local browser UI on http://127.0.0.1:8000
python3 tools/update_team_status.py --team "France" --form 0.2 --injury 0.04 --news 0.05 --note "effectif quasi complet"
python3 tools/bootstrap_team_status.py            # create missing team_status rows for all rated teams
python3 tools/build_odds_template.py --matchday 1 --out data/odds_md1.template.json
python3 tools/snapshot_predictions.py             # freeze pre-match predicted scores in fixtures.json
```

## UI (local one-page app)

Run:

```bash
python3 ui.py
```

Then open `http://127.0.0.1:8000`.

The UI shows one row per game with:
- exact score guess + confidence %
- bet recommendation + confidence %
- flags and compact match cards grouped by matchday (better dense overview)
- only core results visible by default, with important details in an accordion
- data-health traffic light (green/orange/red) to decide if betting mode should be trusted
- one-click ticket suggestions:
  - single safe bet (10 EUR)
  - safe combo bet (1 EUR) with higher combined odds

If data health is **critical**, the UI blocks ticket generation until fixtures/ratings/team status are refreshed.

Controls in the page:
- `matchday` (1-3, leave blank to show all matchdays at once)
- `date` (YYYY-MM-DD, once fixture dates are filled)
- `odds_file` (optional JSON like `data/odds_md1.json`)
- `no_auto=1` to disable automatic rating updates from completed results
- `Generate safe bets (10EUR + 1EUR combo)` button

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
| `data/team_status.json` | injuries/suspensions/form/news signals | update frequently (manual/Claude/automation) |
| `data/expert_sources/*.json` | trusted pundit priors (e.g. Wiloo) | edit by hand or ask Claude with the pundit's calls |
| `data/bracket.json` | WC2026 knockout tree (R32→final, FIFA structure) | static — only edit if FIFA changes the format |
| `data/history.json` | historical WC knockout base rates (calibration targets) | static reference, sourced |
| `data/outrights.json` | manual overlay for long-term markets the API lacks (finalist, group winner…) | **ask Claude** to dictate the odds; the `champion` market is auto-fetched from The Odds API in prod |

## Phases finales — tournament simulation (`engine/tournament.py`)
Once the knockouts loom, single-match probabilities are not enough: who reaches
the R32/16/quarters/semis/final, what the bracket will look like, and each
team's title odds need a **forward Monte-Carlo** of the whole remaining
tournament. Each simulation samples every unplayed group game from the *same*
Dixon-Coles score matrix the per-match prono uses (so the two can never
disagree), builds the 12 final tables (top-2 + the 8 best thirds), allocates the
thirds to FIFA's R32 slots (`data/bracket.json`), then plays the bracket as
knockout ties — 90′, tempo-damped extra time, near-coin-flip shootout — grounded
in historical World Cup base rates (`data/history.json`, checked by
`tournament.calibration_check`). It feeds the **Phases finales** UI tab and
`engine/outrights.py`, which flags value on long-term markets the same safe way
single bets are (de-vig → shrink to market → edge + EV → capped fractional
Kelly). Knockouts are ~2/3 favourite, so outrights MUST come from this sim, never
from chaining single-match favourites.

Outright odds source: in prod the **champion (winner)** market is auto-fetched
from The Odds API (`engine/odds_fetch.ensure_outrights`, same `ODDS_API_KEY`,
cooldown + credit guard as the 1X2 feed — only the Phases finales tab triggers a
fetch). Markets the API doesn't carry for soccer (finalist, group winner…) come
from the manual `data/outrights.json` overlay, which wins on any conflict.

### Cotes (The Odds API)
L'onglet Paris et l'analyse value ont besoin de cotes bookmaker. Deux options :

- **Cotes auto (recommandé)** : créez une clé gratuite sur
  [the-odds-api.com](https://the-odds-api.com), puis exposez-la via la variable
  d'environnement `ODDS_API_KEY` (ou `odds_api_key`), ou collez-la dans le
  fichier `data/odds_api_key.txt`. Les cotes se chargent ensuite toutes seules
  au chargement de l'onglet Paris (avec cooldown pour économiser les crédits).
- **Fichier manuel (avancé)** : générez un gabarit avec
  `python3 tools/build_odds_template.py --matchday 1 --out data/odds_md1.json`,
  remplissez les cotes décimales `[domicile, nul, extérieur]`, puis passez
  `?odds_file=data/odds_md1.json` dans l'URL (ou `--odds-file` en CLI).

### Expert sources (pundit priors)
A trusted human forecaster (e.g. the YouTuber **Wiloo**) is folded in as a
small, **bounded, auditable** prior — never an override (he has no crystal
ball). Each source is one JSON file in `data/expert_sources/`, with a per-team
`lean` (-2..+2 vs the team's Elo), `confidence` (0..1) and audit fields
(`stage_call`, `quote`). `engine/expert_signals.py` converts that into a capped
Elo nudge applied right after team-status signals:

```
delta = lean/2 * confidence * trust * cap_elo   (bounded to ±cap_elo, default ±35)
```

`trust` (0..1, per source) is the recalibration dial: log the source's
outright/stage calls, score them after the group stage, and raise/lower `trust`
based on how right they were — the same "prove the edge is real" logic as the
CLV tracker. An empty `teams: {}` block is a no-op.

One source is active today: `wiloo_wc2026.json` (trust 1.0).
`_mpp_strategy_2026.json` (a friend's MPP playbook PDF) is kept **archived**
(the `_` prefix means the loader never reads it): it was captured to benchmark
the engine against his strategy, not to feed predictions. Drop the prefix to
activate it. If several sources are ever active, overlapping leans stack by
design — and the sum stays bounded by `GLOBAL_CAP_ELO` — but beware that
pundits watching the same games are *correlated*, not independent evidence.

### MPP meta-game (x2 + league position + knockouts)

MPP is a *ranking* game against other humans, so expected points is not always
the right target. Three tools cover the meta layer:

- **x2 bonus** (`engine/x2.py`): the one-per-tournament doubler. `--loop` now
  prints the best target of the slate (highest E[MPP] = the x2's marginal
  gain) plus timing advice — never on MD1, comeback weapon in the groups when
  trailing 80+, R32 only on a standout, **R16 = the optimal window**, QF = last
  call, leaders hold it as late insurance. Override the stage with
  `--x2-stage r16`, feed your position with `--points-behind 120` / `--leading`.
- **League-position modes** (`mpp.recommend(mode=...)`): `ev` (default,
  maximise expected points), `protect` (leading: most likely outcome + most
  likely exact score, no rarity chasing), `chase` (trailing: only scorelines
  carrying a >= "tres rare" bonus — maximise the big-haul tail, not the mean).
  CLI: `--mpp-mode protect|ev|chase`, or `--mpp-mode auto --rank 12
  --league-size 20 --points-behind 90` to derive it.
- **Knockout (120') scoring** (`mpp.recommend(knockout=True)`): MPP counts
  extra time and never penalties, while the Poisson model describes 90
  minutes. For knockout fixtures every 90' draw is convolved with a
  tempo-damped 30' Poisson before optimising, so "1-1 then an ET winner"
  is priced as the 2-1 it ends as. Wired automatically through
  `engine/prediction.py` (display + freeze) once knockout fixtures exist;
  available today via `--match ... --knockout`.

### Autonomous mode (no manual data edits)
- By default, `predict.py`, `ui.py`, and `api/index.py` run an autonomous refresh step before predictions.
- The refresh step automatically:
  - pulls live Elo ratings from `eloratings.net` TSV feeds
  - updates `home_adv` in fixtures (host teams boosted, others neutral)
  - ensures `team_status` coverage for all rated teams
  - refreshes saved predicted scores in `fixtures.json` when inputs change
- Built-in cooldown avoids hitting remote sources too frequently.
- CLI controls:
  - `--no-auto-refresh` disables autonomous refresh for a run
  - `--auto-refresh-force` forces an immediate refresh (ignores cooldown)

### Data quality + team signals
- `engine/data_quality.py` computes a health score (freshness/completeness checks).
- `engine/team_signals.py` converts team status (injury/suspension/form/news) into Elo deltas before prediction.
- `--health-report` prints the quality report in CLI before cards/loops.
- `--coverage-report` prints exactly what is missing for prediction quality:
  - estimated ratings count
  - team status coverage vs total teams
  - fixture-level `home_adv` coverage
- `tools/update_team_status.py` updates `data/team_status.json` quickly:

```bash
# single team update
python3 tools/update_team_status.py --team "South Korea" --form -0.15 --injury 0.10 --news 0.12 --note "incertitude sur un titulaire"

# bulk merge from a patch file
python3 tools/update_team_status.py --merge-file data/team_status_patch.json --source morning_digest

# strict check: fail if any team misses one required signal key
python3 tools/update_team_status.py --merge-file data/team_status_patch.json --strict

# bootstrap missing teams with neutral defaults
python3 tools/bootstrap_team_status.py --note "seeded default"

# create a fillable odds board template (id and match-label keys)
python3 tools/build_odds_template.py --matchday 1 --out data/odds_md1.template.json
```

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

# keep only stronger picks and a tighter Claude queue
python3 predict.py --matchday 1 --loop --min-pick-prob 0.55 --review-top 8

# daily one-page card by calendar date (after fixture dates are filled)
python3 predict.py --date 2026-06-11 --sheet
```

### Daily update workflow
1. After games finish, write final scores into `data/fixtures.json`:
  - `actual_home`
  - `actual_away`
2. Before new games start, freeze model predictions (so you can compare later):
  - `python3 tools/snapshot_predictions.py`
  - adds `predicted_home`, `predicted_away`, `predicted_at` in fixtures
3. Run the daily card:
  - `python3 predict.py --matchday N --sheet`
  - or `python3 predict.py --date YYYY-MM-DD --sheet`

By default, `predict.py` automatically applies all completed fixture results to
ratings before generating new predictions. Use `--no-auto-update` if you need
the frozen baseline ratings for comparison/backtesting.

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
