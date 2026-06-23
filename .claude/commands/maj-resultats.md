---
description: Met à jour data/fixtures.json en autonomie — scores des matchs joués, horaires (kickoff_utc) des matchs à venir, et peuplement du tableau final (Round of 32) une fois la phase de groupes terminée — puis déploie. Conçu pour tourner en session programmée (sans intervention de Baptiste).
allowed-tools: Bash, Read, Edit, WebSearch, WebFetch, Glob, Grep
---

# /maj-resultats — résultats + horaires en autonomie

Cinq jobs, dans cet ordre :
- **A. Scores** : remplir `actual_home`/`actual_away` des matchs **terminés**
  encore vides.
- **B. Horaires** : renseigner `kickoff_utc` (instant UTC du coup d'envoi) des
  matchs **à venir** qui ne l'ont pas encore — l'UI en dérive la date + l'heure
  Europe/Paris (`ui._apply_paris_kickoffs`), donc un horaire faux/absent fausse
  les dates affichées et l'ordre chronologique.
- **C. Forme** : adapter le modèle aux nouveaux résultats en recalculant le
  signal **forme** de `data/team_status.json` (`python3 tools/recompute_form.py`).
  C'est la seule adaptation persistée du modèle ici : l'Elo, lui, s'ajuste déjà
  tout seul au runtime (`updater.apply_completed_results`, voir « Hors périmètre »).
- **D. Règlement des paris** : régler les paris Winamax en cours d'après les
  scores qui viennent d'être saisis (`python3 tools/settle_bets.py`), pour que
  le bilan P&L/ROI de la page Paris reste à jour sans dictée de Baptiste.
- **E. Tableau final (16es)** : une fois la phase de groupes **terminée**,
  déterminer les qualifiés (1ers, 2es, 8 meilleurs 3es) et peupler les 16 matchs
  du **Round of 32** dans `data/fixtures.json`, pour pouvoir les pronostiquer.

Le tout sans que Baptiste ait à dicter quoi que ce soit. Pensé pour une session
**programmée** (trigger récurrent Claude Code web). Une exécution = un cycle
complet ci-dessous.

## Règle d'or
En cas de **doute** (score divergent entre sources, match arrêté / reporté /
**pas encore commencé** ou en cours, équipe mal appariée), **on NE saisit PAS**
ce match : on le laisse vide et on le **signale** dans le rapport final pour
saisie manuelle. Un match dont le **coup d'envoi (`kickoff_utc`) est dans le
futur** n'a par définition pas de score : ne jamais l'inscrire, même si une
source en affiche un (pronostic, autre match, confusion d'appariement). Mieux
vaut un trou qu'un faux score — les scores nourrissent le rating **et les value
bets réels** (cf. `engine/updater.apply_completed_results`).

## Procédure

### A. Scores des matchs joués

1. **Cibler les matchs à saisir.** Lister les fixtures **dont le coup d'envoi
   est déjà passé** (donc plausiblement terminées) ET dont
   `actual_home`/`actual_away` sont `null`. On compare l'instant **`kickoff_utc`**
   à maintenant — surtout **pas** la date calendaire seule : un match du jour qui
   ne démarre que ce soir a `date == aujourd'hui` mais n'a pas encore eu lieu, et
   le saisir produit un **faux score** (cf. Règle d'or). Marge de ~2 h après le
   coup d'envoi pour viser un match réellement fini :
   ```bash
   python3 -c "
   import json, datetime
   now = datetime.datetime.now(datetime.timezone.utc)
   m = json.load(open('data/fixtures.json'))['matches']
   def joue(x):
       ko = x.get('kickoff_utc')
       if ko:  # coup d'envoi connu : exiger qu'il soit passé depuis ~2 h
           t = datetime.datetime.fromisoformat(ko.replace('Z', '+00:00'))
           return now >= t + datetime.timedelta(hours=2)
       # horaire inconnu : repli prudent sur la veille ou avant (jamais aujourd'hui)
       return (x.get('date') or '9999') < now.date().isoformat()
   todo = [x for x in m if x.get('actual_home') is None
           and x.get('actual_away') is None and joue(x)]
   for x in todo:
       print(x['id'], x.get('kickoff_utc') or x['date'], x['home'], 'vs', x['away'])
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

### C. Adapter le modèle aux résultats (forme)

7. **Recalculer la forme** depuis les scores qui viennent d'être saisis. À ne
   lancer **que si** des scores ont été écrits en A (sinon, rien à recalculer) :
   ```bash
   python3 tools/recompute_form.py        # n'écrit que si la forme change
   ```
   L'outil ne touche **que** le champ `form` de chaque équipe ayant joué
   (`engine/form.py`) — blessures / suspensions / news / notes (couche
   ask-Claude) sont préservées. Il est idempotent : sans changement, il n'écrit
   rien (pas de diff parasite). La forme est volontairement **orthogonale à
   l'Elo** (streak récent W/N/D pondéré, léger tilt adversaire, jamais la marge
   de buts que l'Elo possède déjà) — pas de double comptage. En cas de doute sur
   un score (match sauté en A), ce match n'a pas été saisi : il ne pèse donc pas
   sur la forme, ce qui est correct.

### D. Règlement des paris Winamax

7bis. **Régler les paris** dont les matchs viennent d'être saisis. À ne lancer
   **que si** des scores ont été écrits en A (sinon rien de neuf à régler) :
   ```bash
   python3 tools/settle_bets.py        # n'écrit que si un statut change
   ```
   L'outil est **déterministe et idempotent** (logique argent testée,
   `engine/common.settle_status` + `tests/test_bets.py`) : il ne fait que passer
   un pari `en_cours` à `gagne`/`perdu` une fois ses jambes décidées — un combiné
   **perd dès qu'une** jambe est perdue, **gagne** seulement quand **toutes** sont
   jouées et gagnées. Il ne touche jamais un pari déjà réglé et **n'invente jamais
   un remboursement**. Les cas spéciaux (sélection **annulée / cote void / cash
   out**, ou un pari sans champ `legs`) ne sont **pas** réglés par l'outil :
   les **signaler** dans le rapport pour règlement manuel (Baptiste dicte, on écrit
   `data/bets.json`). En cas de doute sur un score (match sauté en A), le match
   n'est pas saisi : le pari reste donc `en_cours`, ce qui est correct.

### E. Tableau final — Round of 32 (16es de finale)

Ne concerne que la **fin de la phase de groupes**. Tant que les 12 groupes ne
sont pas terminés, cette étape n'écrit rien (l'outil le dit lui-même).

8. **Rapport de qualification** (lecture seule) :
   ```bash
   python3 tools/build_knockout_r32.py
   ```
   Il affiche, par groupe, les **1er/2e** et le **3e**, le **classement des 12
   3es** avec les **8 qualifiés**, et la grille des 16 matchs R32 (numéros 73-88,
   dates et villes figées) avec les emplacements encore à résoudre (`<1E>`,
   `<3:ABCDF>`…). Tout ce qui n'est pas dérivable des scores est listé en bas
   (« À résoudre avant écriture »).
   - S'il reste des groupes **non terminés** → rien à faire ici ce cycle, on
     passe à la finalisation (ne pas forcer).

9. **Confirmer les appariements sur source officielle.** Les **24** 1ers/2es
   sont déterministes (l'outil les calcule). La **seule** chose non dérivable des
   scores est l'allocation des **8 meilleurs 3es** aux 8 emplacements « 3e » (FIFA
   la tire de sa table à 495 combinaisons une fois les 8 groupes connus). Comme
   pour les scores : **on vérifie le tableau R32 officiel sur le web** (FIFA,
   ESPN…), **on ne devine jamais** (Règle d'or).
   - **Recoupement obligatoire** : les 1ers/2es du rapport doivent coïncider
     **exactement** avec le bracket officiel. Toute divergence — ou une **égalité
     non tranchée** signalée par le rapport (`Égalité non tranchée …`) — → on
     **n'écrit pas**, on **signale** pour résolution manuelle. Mieux vaut un trou
     qu'un mauvais appariement.

10. **Écrire l'allocation des 3es** dans `data/knockout_seed.json` (couche
    ask-Claude, comme `bets.json`/`odds.json`) — pour chaque match à emplacement
    « 3e », la **lettre du groupe** dont le 3e y joue (doit appartenir aux
    candidats que le rapport imprime) :
    ```json
    { "thirds_by_match": {"74":"B","77":"D","79":"C","80":"K","81":"F","82":"A","85":"G","87":"L"} }
    ```

11. **Composer + écrire les fixtures R32** :
    ```bash
    python3 tools/build_knockout_r32.py --write
    ```
    Il écrit les 16 fixtures (équipes réelles, dates/villes figées, `stage:
    round_of_32`) dans `data/fixtures.json`. Il **refuse** d'écrire si un
    emplacement reste non résolu, si une équipe apparaît deux fois, ou si un 3e
    est hors de ses candidats — dans ce cas, **signaler** et ne rien committer
    pour cette étape. Les R32 sont alors **pronosticables** (le modèle les note
    sur la distribution 120', `stage != group`).
    - Les `kickoff_utc` des R32 sont laissés vides : l'**étape B** les remplira au
      prochain passage dans sa fenêtre (le R32 démarre le 28 juin). Aucun
      `predicted_*` n'est figé ici — le gel se fait par le chemin habituel quand
      le coup d'envoi approche.

### Finalisation (commun A + B + C + D + E)

12. **Hygiène des effets de bord `data/`** (règle CLAUDE.md). Si une commande a
   fait tourner l'UI/`autonomous_refresh` et muté `data/ratings.json` sans
   intention, restaurer. `data/team_status.json` peut, lui, avoir été modifié
   **volontairement** par l'étape C — dans ce cas on le **garde** :
   ```bash
   git status --short
   git restore data/ratings.json                      # toujours : jamais modifié à la main ici
   git restore data/team_status.json                  # SEULEMENT si l'étape C n'a rien écrit
   ```
   Doivent rester modifiés : `data/fixtures.json` (A/B/E) et, si la forme a bougé,
   `data/team_status.json` (C) ; `data/knockout_seed.json` si l'étape E a écrit.

13. **Valider** : JSON correct + récap justesse cohérent :
   ```bash
   python3 -c "import json; json.load(open('data/fixtures.json')); json.load(open('data/team_status.json')); print('JSON ok')"
   python3 -c "
   from engine import data
   done=[x for x in data.load_fixtures() if x.get('actual_home') is not None]
   print(len(done), 'matchs terminés au total')
   "
   ```

14. **Committer + déployer.** Ce job vise la **prod** : commit sur la branche
    courante, push, puis fast-forward de `main` et push `main` (= déploiement
    Vercel). Message clair couvrant ce qui a changé (scores, horaires, forme, R32),
    p.ex. : `git commit -m "Maj auto <date> : résultats G07 1-1 + forme MAJ"`.
    N'ajouter chaque fichier que s'il a effectivement changé :
    ```bash
    git add data/fixtures.json
    git add data/team_status.json   # seulement si l'étape C a écrit (sinon ignorer)
    git add data/bets.json          # seulement si l'étape D a réglé des paris (sinon ignorer)
    git add data/knockout_seed.json # seulement si l'étape E a peuplé le R32 (sinon ignorer)
    git commit -m "Maj auto du $(date +%F) (résultats + horaires + forme + paris)"
    git push -u origin "$(git branch --show-current)"
    git fetch origin main && git checkout main && git merge --ff-only -
    git push -u origin main
    ```
    S'il n'y a eu **ni score, ni horaire, ni forme, ni R32** à écrire → ne pas
    faire de commit vide.

15. **Rapport final** (toujours) : lister ce qui a été **saisi** (scores,
    horaires), la **forme** recalculée (équipes dont le signal a bougé), le **R32
    peuplé** le cas échéant, et surtout ce qui a été **sauté** et pourquoi (à
    traiter à la main). Si tout est propre et rien à signaler, un résumé d'une
    ligne suffit.

## Hors périmètre
- **Saisie d'un nouveau pari** (placer un pari, l'ajouter à `data/bets.json`)
  reste **manuel** : Baptiste dicte ses tickets Winamax, on écrit le JSON. Ce
  playbook ne fait que **régler** (gagné/perdu) les paris déjà enregistrés, à
  partir des scores. Les **remboursements / cotes void / cash out** restent
  aussi manuels (l'outil ne les devine pas — il les laisse `en_cours` et on
  les signale).
- **L'Elo n'est pas recalculé ni persisté ici** : `apply_completed_results`
  l'ajuste tout seul au runtime à partir des scores saisis (deltas locaux sur la
  baseline figée). Le persister serait un double comptage (cf. ui.py, commentaire
  sur l'overlay eloratings.net). La seule adaptation persistée est la **forme**
  (étape C), canal séparé.
