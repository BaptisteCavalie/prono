# Project Work Log

## 2026-06-23 (bis) — Contexte compétition (enjeu / motivation J3)

### Summary
- **Le modèle ignorait l'état de la compétition** : il notait la *force* (Elo),
  jamais la *situation*. D'où des « value » sur des équipes que le tableau avait
  déjà réglées (ex. Türkiye éliminée poussée à miser).
- **Effet motivation chiffré sur l'historique** (CDM 2022, J3, 32 perfs
  classées par enjeu vs attente Elo) :
  - déjà **QUALIFIÉE** (fait tourner) : **−1,68 pt/match** (1 v / 4) — effet le + fort
  - **ÉLIMINÉE** (baroud d'honneur) : −0,62 pt/match (0 v / 3)
  - **en lice** (doit gagner) : +0,44 pt/match (+19 % de victoires)
  - Contre-intuitif et confirmé par le qualitatif (France 2022 : 9 changements →
    battue par la Tunisie ; Brésil/Portugal 2022 ; 2018 Russie 0-3, Angleterre 0-1).
    Le côté qui ne joue plus rien sous-performe ; le **qualifié qui se repose**
    plus encore que l'éliminé.
- **`engine/standings.py`** (nouveau) : classements de groupe + **simulation
  exhaustive** des matchs restants (≤81 combos) → statut exact `qualified` /
  `eliminated` / `contention`. Malus motivation replié dans le différentiel Elo :
  **qualifiée −85, éliminée −45, en lice 0** (≈ moitié de l'effet brut, prudent,
  ajustable). `apply_stakes` ne touche que les matchs **à venir** → backtest intact.
- Câblage : `ui._analyse_rows` (prono + 1N2 + Nutri reflètent l'enjeu) et le
  **gel** (`autonomous._refresh_prediction_snapshots`) appliquent le MÊME ajust →
  affiché == gelé. **Garde-fou paris** : un *match-poubelle* (deux côtés sans
  enjeu) ne propose **aucun pari** ; un seul côté → autorisé mais **tag**.
  Chip « Sans enjeu » + notes pour la transparence.
- Validation : G23 Türkiye–USA, G53 Norvège–France, etc. → dead rubbers, paris
  bloqués ; G24 Paraguay–Australie (vraie lutte) reste un match normal. 130 tests
  OK (`tests/test_standings.py`), 3 onglets rendent, backtest inchangé.

### Key Files Added/Updated
- engine/standings.py (nouveau), tests/test_standings.py (nouveau)
- ui.py (_analyse_rows + stakes, garde-fou paris, chip + CSS), engine/autonomous.py

## 2026-06-23 — Contre-analyse paris + calibration du modèle

### Summary
- **Recul sur les paris** (17 paris réglés) : **P&L −16,74 € / ROI −19,9 %**.
  Pertes concentrées sur des **favoris « vainqueur » qui ont fait nul** (Belgique-
  Égypte ×2, Iran, Tchéquie-RSA) ou battus par l'outsider (USA-Australie). Les
  gains = favoris nets qui ont tenu (Mexique, Argentine, France, Allemagne).
- **Contre-analyse modèle vs marché** (matchs terminés, reconstruction honnête
  *as-of*, sans fuite forme) :
  - Le modèle déployé (Elo + status + experts) **bat l'Elo brut** sur toutes les
    métriques, mais **reste derrière le marché** (consensus des pronostiqueurs).
  - **Faille = surconfiance des extrêmes** : log-loss 1.105 *pire qu'un 33/33/33*
    (1.099), tirée par des « locks » à 95 % qui ont fait nul (Espagne-Cap-Vert,
    Portugal-RDC). Bucket 90-99 % : hit réel ~57-60 %. Brier/RPS battaient
    l'uniforme, mais la proba elle-même était le point faible.
  - Benchmark externe (web) : Opta supercomputer (Espagne 16,1 % / France 13,0 %
    / Angleterre 11,2 % / Argentine 10,4 %) **corrobore l'ordre du haut de
    tableau** de nos ratings.
- **Amélioration : calibration par température** (`engine/calibration.py`, T=1.5).
  - `p_i' ∝ p_i^(1/T)`, renormalisée. **Monotone → argmax/pick/précision/gel des
    pronos inchangés** ; seule la *confiance* est ramenée vers l'honnêteté.
  - T choisi conservateur : le basin log-loss optimal (~2.0-2.3) **réplique
    hors-échantillon** sur deux tournois (WC2026 44 matchs *et* WC2022 48 matchs).
    1.5 capte ~80 % du gain et garde l'expressivité (un carton à 95 % → ~85 %, pas
    ~75 %).
  - Câblée dans les surfaces de *confiance/EV* uniquement : Solidité/Diagnostics,
    value/EV (`odds.value_1x2`), confiance (`report.confidence`), distribution +
    verdict + Nutri de l'UI. **Score MPP / gel restent sur la grille brute.**
  - Effets mesurés : backtest log-loss **1.113→1.009**, gap calib **+15.8→+6.5pt** ;
    as-of honnête **1.105→1.005** (passe sous l'uniforme) ; proba moyenne de nul
    sur les nuls réels **17 %→23 %** ; +2 matchs « Piège : nul probable » sur les
    à-venir (l'alerte qui manquait aux paris perdus).
- Critics : 121 tests OK (8 nouveaux, `tests/test_temperature.py`, dont la
  régression log-loss WC2022 hors-échantillon). 3 onglets rendent (smoke).

### Key Files Added/Updated
- engine/calibration.py (nouveau), tests/test_temperature.py (nouveau)
- engine/solidity.py, engine/odds.py, engine/report.py, ui.py, tools/calibration.py

## 2026-06-12 (après-midi) — /feature refonte dashboard

### Summary
- Refonte complète de l'UI vers un **dashboard à menu latéral** (desktop-only).
  - **DA révisée** (`design/da.md`) : « poste de pilotage » — sidebar sombre
    chaude (châssis) + canvas papier clair (contenu). Règle cardinale : le
    sombre s'arrête à la nav, jamais sur la donnée de pari. Signature Nutri
    conservée. Validée par Baptiste (checkpoint /da).
  - **Châssis** : `_render_sidebar` (nav 3 entrées server-rendered, actif =
    fond teinté + encre teal lumineux + bordure + aria-current), tokens
    `--nav-*` dans le `:root`. Remplace la tabbar.
  - **Page Matchs unique** : futurs + passés fusionnés ; passés en `<details>`
    replié par défaut (récap Justesse en tête), persistance localStorage,
    dégradation sans JS. `_render_day_sections` extrait (réutilisé).
  - **Filtre pays instantané** (futurs + passés) : compte vivant, état aucun
    résultat, auto-dépli des passés si match, masquage des sections vides.
  - **Diagnostics** promu en vue de la sidebar. Mobile non ciblé.
- Critics : design `ship` (tour 2 ; 2 tours, highs corrigés : pluriel, label
  chip prono, double-panel Diagnostics), code `ship` (tour 2). 45 tests OK.
- Pattern `patterns/chassis-dashboard.md` (sidebar + repli + filtre).

### Key Files
- ui.py (_render_sidebar, _render_day_sections, _render_page réécrit, tokens
  --nav-*, JS filtre + repli, nettoyage CSS mort)
- design/da.md (révision dashboard), patterns/chassis-dashboard.md (nouveau)
- tests/test_scoring.py (routage + pluriel), CLAUDE.md (forme UI)

## 2026-06-12

### Summary (/feature — scores réels + récap justesse pronos)
- La CDM a commencé : ajout du suivi réel vs prono sur l'onglet **Passés**.
  - **Couche ask-Claude** : scores réels J1 récupérés et vérifiés (web), écrits
    dans `data/fixtures.json` : G01 Mexico 2-0 Afrique du Sud (prono 2-0 →
    exact), G02 Corée du Sud 2-1 Tchéquie (prono 2-0 → bon résultat). Canada-
    Bosnie est en réalité le 12/06 (pas encore joué). L'outil ne touche jamais
    le réseau lui-même (doctrine projet).
  - **Logique de classement** pure et testée (`engine.common.classify_prono`,
    `tally_pronos`) : exact (score juste) / bon (résultat 1N2 juste, score faux)
    / erreur (résultat faux), alignée Mon Petit Prono. Verdict calculé seulement
    si le prono était figé avant le coup d'envoi.
  - **Vis-à-vis par match** : tag verdict discret (pastille + texte, double
    encodage) accolé aux chips Réel/Prono.
  - **Récap cumul-tournoi** « Justesse des pronos » en tête des Passés : barre
    segmentée 100 % (exact·bon·erreur), compteurs mono, échantillon en clair,
    garde-fou petit N (< 5 matchs) + note anti-certitude. Pas de donut : barre
    plus lisible/accessible pour 3 parts (pattern `recap-justesse-pronos`).
  - Couleurs : rampe dédiée `--recap-exact/bon/erreur` (teal → teal désaturé →
    gris froid), hors rôles ok/warn/alert et hors gamme Nutri A–E.
- Critics : design `ship` (3 minor + 1 nit corrigés), code `ship` (0 issue,
  dette `classify_prono` durcie). Suite : 42 tests OK.

### Key Files Added/Updated
- engine/common.py (classify_prono, tally_pronos, PRONO_CATEGORIES)
- ui.py (_render_recap, verdict par ligne, tokens + CSS récap/verdict)
- data/fixtures.json (scores réels G01, G02)
- tests/test_scoring.py (nouveau), tools/screenshots.sh (nouveau)
- patterns/recap-justesse-pronos.md (nouveau), CLAUDE.md (doctrine scores réels)

## 2026-06-10

### Summary (audit /critique + fixes)
- Audit complet (/critique) par design-critic + code-reviewer, puis correction des majors et minors retenus :
  - Sécurité : le paramètre `?odds_file=` est désormais confiné sous la racine du projet (path traversal bloqué), erreurs sans écho de chemin.
  - Déduplication : l'orchestration web vit dans `ui.build_page(params)`, partagée par le serveur local et `api/index.py` (adaptateur Flask minimal) ; helpers communs (`split_match`, `match_key`, `find_match_odds`, `parse_date`, `load_odds_board`) centralisés dans `engine/common.py` pour la CLI et le web.
  - Erreurs : messages FR actionnables (`UserFacingError`) pour cotes/date invalides ; les exceptions inattendues sont loggées côté serveur et remplacées par un message générique.
  - Code mort : `_default_odds_file`, paramètres `action`/`applied_results` de `_render_page`, variable `eb` (mpp), import `Tuple` (expert_signals), f-string sans placeholder (bet.py).
  - Robustesse : `bankroll=nan/inf` rejeté (`math.isfinite`), `mimetype` Flask remplacé par `content_type`.
  - Design : focus clavier en `--brand` plein (3:1+), palette entièrement tokenisée dans `:root` (`--accent` mort supprimé), badge « Miser » en `--ok-strong` (AA), segment Nul assombri, graisses normalisées 400/700, `.legend` limité à 75ch, dates de journée en `<h2>`, summary « Détails » allégé, pastille de maj non focusable.
  - Copy : onglet Paris avec sous-titre dédié et état vide unique quand aucune cote n'est chargée (plus de « Aucune value détectée » mensonger ni de stats à zéro), guidance cotes canonique (clé The Odds API, documentée dans le README), jargon CLI retiré de l'UI, « Solidité n/a/100 » remplacé par un libellé propre.
- Le crash `predict.py --match "A vs B"` repéré pendant l'audit a été corrigé en parallèle sur main (couche MPP, voir ci-dessous).

### Key Files Added/Updated (audit)
- engine/common.py (nouveau)
- ui.py, api/index.py, predict.py, bet.py
- engine/mpp.py, engine/expert_signals.py
- README.md (section « Cotes (The Odds API) »)

### Summary (MPP meta-game layer)
- Compared the engine against a friend's MPP strategy PDF and ported the meta-game layer it exposed:
  - `engine/x2.py`: x2 bonus policy — best target of a slate (highest E[MPP] = the doubler's marginal gain) + codified timing tree (never MD1, group comeback at 80+ behind, R32 standout only, R16 optimal window, QF last call, leaders hold as insurance). Surfaced in `--loop`.
  - League-position modes in `mpp.recommend(mode=...)`: `ev` / `protect` (leader: modal pick, no rarity chasing) / `chase` (trailing: >= "tres rare" bonus only). CLI `--mpp-mode`, `--rank`, `--league-size`, `--points-behind`, `--leading`.
  - Knockout 120' scoring in `mpp.recommend(knockout=True)`: MPP counts extra time (never pens); 90' draws are convolved with a tempo-damped 30' Poisson. Wired through `engine/prediction.py` (display + freeze stay identical) and `--match ... --knockout`.
- New expert source `data/expert_sources/mpp_strategy_2026.json` (trust 0.7): the friend's group-standings leans (USA +2, Paraguay -2, Japan +1, Netherlands -1, ...), outrights (France / Mbappé), audit quotes.
- Bug fixes:
  - `predict.py --match` crashed (`TypeError` in report.confidence): the what-if match dict was missing `home`/`away` keys, so `prediction.analyse_match` returned None.
  - Host nations listed as the *away* team silently lost their +65 home boost (`autonomous._refresh_home_adv` only checked the home side). Hosts away now get a negative `home_adv`; G05/G11/G23 fixed in fixtures.json and snapshots refrozen.
- Follow-up (same day): the friend's expert source is **archived** (renamed `_mpp_strategy_2026.json`, never loaded) — it was captured to benchmark the engine vs his strategy, not to feed predictions. Snapshots refrozen on maths + Wiloo only (G19 1-0, G31 2-0, G36 2-0 reverted; G23 keeps the host-fix 2-0).
- New tests: `tests/test_mpp_x2.py` (knockout distribution, modes, x2 policy, both bug regressions). Suite: 31 tests OK.

### Key Files Added/Updated (MPP)
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
