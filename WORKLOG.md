# Project Work Log

## 2026-06-10

### Summary
- Compared the engine against a friend's MPP strategy PDF and ported the meta-game layer it exposed:
  - `engine/x2.py`: x2 bonus policy — best target of a slate (highest E[MPP] = the doubler's marginal gain) + codified timing tree (never MD1, group comeback at 80+ behind, R32 standout only, R16 optimal window, QF last call, leaders hold as insurance). Surfaced in `--loop`.
  - League-position modes in `mpp.recommend(mode=...)`: `ev` / `protect` (leader: modal pick, no rarity chasing) / `chase` (trailing: >= "tres rare" bonus only). CLI `--mpp-mode`, `--rank`, `--league-size`, `--points-behind`, `--leading`.
  - Knockout 120' scoring in `mpp.recommend(knockout=True)`: MPP counts extra time (never pens); 90' draws are convolved with a tempo-damped 30' Poisson. Wired through `engine/prediction.py` (display + freeze stay identical) and `--match ... --knockout`.
- New expert source `data/expert_sources/mpp_strategy_2026.json` (trust 0.7): the friend's group-standings leans (USA +2, Paraguay -2, Japan +1, Netherlands -1, ...), outrights (France / Mbappé), audit quotes.
- Bug fixes:
  - `predict.py --match` crashed (`TypeError` in report.confidence): the what-if match dict was missing `home`/`away` keys, so `prediction.analyse_match` returned None.
  - Host nations listed as the *away* team silently lost their +65 home boost (`autonomous._refresh_home_adv` only checked the home side). Hosts away now get a negative `home_adv`; G05/G11/G23 fixed in fixtures.json and snapshots refrozen.
- New tests: `tests/test_mpp_x2.py` (knockout distribution, modes, x2 policy, both bug regressions). Suite: 31 tests OK.

### Key Files Added/Updated
- engine/x2.py (new), engine/mpp.py, engine/prediction.py, engine/report.py, engine/autonomous.py
- predict.py, ui.py, README.md
- data/expert_sources/mpp_strategy_2026.json (new), data/fixtures.json
- tests/test_mpp_x2.py (new)

## 2026-06-05

### Summary
- Initialized and checkpointed the repository.
- Implemented a matchday loop mode with confidence ranking, value flags, and a Claude review queue.
- Added filtering controls and date selector support for loop mode.
- Added daily one-page sheet mode with exactly two outputs per game:
  - exact score guess + confidence percent
  - bet recommendation + confidence percent
- Added automatic rating updates from completed fixtures before prediction runs.
- Added a local web UI using Python stdlib with improved accessibility and responsive layout.

### Commits
1. b7a5f6d - Initial WC2026 prediction engine baseline
2. 9b1e4a3 - Add matchday loop command with confidence ranking and review queue
3. 986f93b - Enhance loop CLI with date selection and filtering controls
4. 0edbe8d - Add daily sheet mode and auto rating updates from results
5. 061d43d - Add local web UI with improved accessibility and responsive layout

### Key Files Added/Updated
- predict.py
- engine/updater.py
- ui.py
- README.md

### Commands Added for Daily Use
- python3 predict.py --matchday 1 --sheet
- python3 predict.py --date 2026-06-11 --sheet
- python3 predict.py --matchday 1 --loop --min-pick-prob 0.55 --review-top 8
- python3 ui.py

### Data Update Workflow
1. Write completed match scores in data/fixtures.json:
   - actual_home
   - actual_away
2. Run sheet mode to regenerate updated predictions:
   - python3 predict.py --matchday N --sheet
   - or python3 predict.py --date YYYY-MM-DD --sheet
3. Optional browser workflow:
   - python3 ui.py
   - open http://127.0.0.1:8000

### Current Repository State
- Branch: main
- Working tree: clean

### Notes
- Date-based selection is implemented and ready. It returns no fixtures until real dates are populated in data/fixtures.json.
- Auto-update of ratings from completed fixtures is enabled by default; pass --no-auto-update to compare with frozen baseline ratings.
