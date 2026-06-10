# Project Work Log

## 2026-06-10

### Summary
- Audit complet (/critique) par design-critic + code-reviewer, puis correction des majors et minors retenus :
  - Sécurité : le paramètre `?odds_file=` est désormais confiné sous la racine du projet (path traversal bloqué), erreurs sans écho de chemin.
  - Déduplication : l'orchestration web vit dans `ui.build_page(params)`, partagée par le serveur local et `api/index.py` (adaptateur Flask minimal) ; helpers communs (`split_match`, `match_key`, `find_match_odds`, `parse_date`, `load_odds_board`) centralisés dans `engine/common.py` pour la CLI et le web.
  - Erreurs : messages FR actionnables (`UserFacingError`) pour cotes/date invalides ; les exceptions inattendues sont loggées côté serveur et remplacées par un message générique.
  - Code mort : `_default_odds_file`, paramètres `action`/`applied_results` de `_render_page`, variable `eb` (mpp), import `Tuple` (expert_signals), f-string sans placeholder (bet.py).
  - Robustesse : `bankroll=nan/inf` rejeté (`math.isfinite`), `mimetype` Flask remplacé par `content_type`.
  - Design : focus clavier en `--brand` plein (3:1+), palette entièrement tokenisée dans `:root` (`--accent` mort supprimé), badge « Miser » en `--ok-strong` (AA), segment Nul assombri, graisses normalisées 400/700, `.legend` limité à 75ch, dates de journée en `<h2>`, summary « Détails » allégé, pastille de maj non focusable.
  - Copy : onglet Paris avec sous-titre dédié et état vide unique quand aucune cote n'est chargée (plus de « Aucune value détectée » mensonger ni de stats à zéro), guidance cotes canonique (clé The Odds API, documentée dans le README), jargon CLI retiré de l'UI, « Solidité n/a/100 » remplacé par un libellé propre.
- Bug préexistant repéré (non corrigé, hors scope) : `python3 predict.py --match "A vs B"` crashe (`prediction.analyse_match` renvoie None pour un match hors calendrier, `report.confidence` déréférence). Présent sur HEAD avant ces changements.

### Key Files Added/Updated
- engine/common.py (nouveau)
- ui.py, api/index.py, predict.py, bet.py
- engine/mpp.py, engine/expert_signals.py
- README.md (section « Cotes (The Odds API) »)

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
