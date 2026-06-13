---
description: Récupère les scores des matchs joués non saisis, les écrit dans data/fixtures.json, et déploie. Conçu pour tourner en session programmée (sans intervention de Baptiste).
allowed-tools: Bash, Read, Edit, WebSearch, WebFetch, Glob, Grep
---

# /maj-resultats — saisie autonome des résultats joués

Objectif : remplir `actual_home`/`actual_away` des matchs **terminés** mais
encore vides dans `data/fixtures.json`, puis déployer — sans que Baptiste ait à
dicter les scores. Pensé pour une session **programmée** (trigger récurrent
Claude Code web). Une exécution = un cycle complet ci-dessous.

## Règle d'or
En cas de **doute** (score divergent entre sources, match arrêté / reporté /
en cours, équipe mal appariée), **on NE saisit PAS** ce match : on le laisse
vide et on le **signale** dans le rapport final pour saisie manuelle. Mieux vaut
un trou qu'un faux score — les scores nourrissent le rating **et les value bets
réels** (cf. `engine/updater.apply_completed_results`).

## Procédure

1. **Cibler les matchs à saisir.** Lister les fixtures dont la date est
   aujourd'hui ou avant ET dont `actual_home`/`actual_away` sont `null` :
   ```bash
   python3 -c "
   import json, datetime
   today = datetime.date.today().isoformat()
   m = json.load(open('data/fixtures.json'))['matches']
   todo = [x for x in m if (x.get('date') or '9999') <= today
           and x.get('actual_home') is None and x.get('actual_away') is None]
   for x in todo:
       print(x['id'], x['date'], x['home'], 'vs', x['away'])
   print('---', len(todo), 'match(s) à vérifier')
   "
   ```
   S'il n'y en a aucun → rien à faire, terminer sans commit (ne pas pousser un
   commit vide).

2. **Récupérer le score réel de chacun** via `WebSearch`/`WebFetch`. Exiger :
   - statut **terminé** (Full Time / score final) — surtout pas un match en cours ;
   - source fiable (ESPN, FIFA, BBC, L'Équipe…) ; en cas de doute, **recouper
     deux sources** et n'écrire que si elles concordent ;
   - bon appariement domicile/extérieur (attention aux noms : Türkiye/Turkey,
     Czechia/Czech Republic, DR Congo, Côte d'Ivoire/Ivory Coast…).
   Tout match arrêté/reporté/ambigu → **on saute** (cf. Règle d'or).

3. **Écrire les scores** dans `data/fixtures.json` avec `Edit` : ne modifier que
   `actual_home` et `actual_away` (entiers) de la ligne du match. Ne **jamais**
   toucher `predicted_*`, `home_adv`, etc.

4. **Hygiène des effets de bord `data/`** (règle CLAUDE.md). Si une commande a
   fait tourner l'UI/`autonomous_refresh` et muté `data/ratings.json` ou
   `data/team_status.json` sans intention, restaurer :
   ```bash
   git status --short
   git restore data/ratings.json data/team_status.json   # seulement si mutés involontairement
   ```
   Seul `data/fixtures.json` doit rester modifié.

5. **Valider** : JSON correct + récap justesse cohérent :
   ```bash
   python3 -c "import json; json.load(open('data/fixtures.json')); print('JSON ok')"
   python3 -c "
   from engine import data
   done=[x for x in data.load_fixtures() if x.get('actual_home') is not None]
   print(len(done), 'matchs terminés au total')
   "
   ```

6. **Committer + déployer.** Ce job vise la **prod** : commit sur la branche
   courante, push, puis fast-forward de `main` et push `main` (= déploiement
   Vercel). Message clair, p.ex. :
   `git commit -m "Résultats du <date> : <G07 1-1, G08 0-2, ...> (saisie auto)"`
   ```bash
   git add data/fixtures.json
   git commit -m "Résultats auto du $(date +%F)"
   git push -u origin "$(git branch --show-current)"
   git fetch origin main && git checkout main && git merge --ff-only -
   git push -u origin main
   ```

7. **Rapport final** (toujours) : lister les matchs **saisis** (avec score) et
   surtout les matchs **sautés** et pourquoi (à saisir à la main). Si tout est
   propre et rien à signaler, un résumé d'une ligne suffit.

## Hors périmètre
- **Règlement des paris Winamax** (gagné/perdu) reste **manuel** : c'est le
  compte réel de Baptiste, il dicte, on écrit `data/bets.json`. Ce playbook ne
  touche qu'aux scores des matchs.
- Le rating n'est pas recalculé ici : `apply_completed_results` s'applique tout
  seul au runtime à partir des scores saisis.
