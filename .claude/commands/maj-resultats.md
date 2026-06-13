---
description: Met à jour data/fixtures.json en autonomie — scores des matchs joués ET horaires (kickoff_utc) des matchs à venir — puis déploie. Conçu pour tourner en session programmée (sans intervention de Baptiste).
allowed-tools: Bash, Read, Edit, WebSearch, WebFetch, Glob, Grep
---

# /maj-resultats — résultats + horaires en autonomie

Deux jobs, dans cet ordre :
- **A. Scores** : remplir `actual_home`/`actual_away` des matchs **terminés**
  encore vides.
- **B. Horaires** : renseigner `kickoff_utc` (instant UTC du coup d'envoi) des
  matchs **à venir** qui ne l'ont pas encore — l'UI en dérive la date + l'heure
  Europe/Paris (`ui._apply_paris_kickoffs`), donc un horaire faux/absent fausse
  les dates affichées et l'ordre chronologique.

Le tout sans que Baptiste ait à dicter quoi que ce soit. Pensé pour une session
**programmée** (trigger récurrent Claude Code web). Une exécution = un cycle
complet ci-dessous.

## Règle d'or
En cas de **doute** (score divergent entre sources, match arrêté / reporté /
en cours, équipe mal appariée), **on NE saisit PAS** ce match : on le laisse
vide et on le **signale** dans le rapport final pour saisie manuelle. Mieux vaut
un trou qu'un faux score — les scores nourrissent le rating **et les value bets
réels** (cf. `engine/updater.apply_completed_results`).

## Procédure

### A. Scores des matchs joués

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

### B. Horaires des matchs à venir

4. **Cibler les matchs sans horaire.** Lister les fixtures **à venir** (non
   joués) qui n'ont pas de `kickoff_utc`, en se limitant à la fenêtre utile
   (p.ex. les ~6 prochains jours, pour ne pas chasser des horaires non encore
   publiés) :
   ```bash
   python3 -c "
   import json, datetime
   horizon = (datetime.date.today() + datetime.timedelta(days=6)).isoformat()
   m = json.load(open('data/fixtures.json'))['matches']
   todo = [x for x in m if x.get('actual_home') is None
           and not x.get('kickoff_utc') and (x.get('date') or '9999') <= horizon]
   for x in todo: print(x['id'], x['date'], x['home'], 'vs', x['away'])
   print('---', len(todo), 'horaire(s) à renseigner')
   "
   ```

5. **Récupérer le coup d'envoi** de chacun (date + heure) via le web, sur une
   source fiable du calendrier officiel (FIFA, ESPN…). Convertir en **UTC**
   (ISO `YYYY-MM-DDThh:mm:ssZ`). Rappel : l'été, Paris = UTC+2 (CEST). Si
   l'horaire n'est pas encore confirmé/publié → **on saute** (Règle d'or), on
   ne devine pas.

6. **Écrire `kickoff_utc`** dans `data/fixtures.json` (juste après `date`, par
   cohérence). Ne pas toucher au champ `date` à la main : l'UI le recalcule
   depuis `kickoff_utc`. Vérifier que la date Paris dérivée est cohérente :
   ```bash
   python3 -c "
   from engine import data; import ui
   fx = data.load_fixtures(); ui._apply_paris_kickoffs(fx)
   for m in fx:
       if m.get('kickoff_utc'):
           print(m['id'], '->', m['date'], m.get('kickoff_paris'), '(FR)')
   "
   ```

### Finalisation (commun A + B)

7. **Hygiène des effets de bord `data/`** (règle CLAUDE.md). Si une commande a
   fait tourner l'UI/`autonomous_refresh` et muté `data/ratings.json` ou
   `data/team_status.json` sans intention, restaurer :
   ```bash
   git status --short
   git restore data/ratings.json data/team_status.json   # seulement si mutés involontairement
   ```
   Seul `data/fixtures.json` doit rester modifié.

8. **Valider** : JSON correct + récap justesse cohérent :
   ```bash
   python3 -c "import json; json.load(open('data/fixtures.json')); print('JSON ok')"
   python3 -c "
   from engine import data
   done=[x for x in data.load_fixtures() if x.get('actual_home') is not None]
   print(len(done), 'matchs terminés au total')
   "
   ```

9. **Committer + déployer.** Ce job vise la **prod** : commit sur la branche
   courante, push, puis fast-forward de `main` et push `main` (= déploiement
   Vercel). Message clair couvrant ce qui a changé (scores et/ou horaires),
   p.ex. : `git commit -m "Maj auto <date> : résultats G07 1-1 + horaires G13/G14"`
   ```bash
   git add data/fixtures.json
   git commit -m "Maj auto du $(date +%F) (résultats + horaires)"
   git push -u origin "$(git branch --show-current)"
   git fetch origin main && git checkout main && git merge --ff-only -
   git push -u origin main
   ```
   S'il n'y a eu **ni score ni horaire** à écrire → ne pas faire de commit vide.

10. **Rapport final** (toujours) : lister ce qui a été **saisi** (scores et
    horaires) et surtout ce qui a été **sauté** et pourquoi (à traiter à la
    main). Si tout est propre et rien à signaler, un résumé d'une ligne suffit.

## Hors périmètre
- **Règlement des paris Winamax** (gagné/perdu) reste **manuel** : c'est le
  compte réel de Baptiste, il dicte, on écrit `data/bets.json`. Ce playbook ne
  touche qu'aux scores des matchs.
- Le rating n'est pas recalculé ici : `apply_completed_results` s'applique tout
  seul au runtime à partir des scores saisis.
