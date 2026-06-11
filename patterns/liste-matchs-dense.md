# Pattern : Liste de matchs dense + report sans erreur

> Date : 2026-06-11 · Contexte d'origine : refonte UI prono

## Le problème
Une liste dense de matchs doit servir trois gestes distincts : détecter ce qui a changé, recopier séquentiellement sans rien rater, transcrire un pari sans erreur. Aujourd'hui le signal de changement (point orange pulsant) est éphémère visuellement, ne dit pas *quoi* a changé, et rien ne garantit l'exhaustivité du report.

## Références (3 max)

### FotMob / Sofascore (ligne de match)
- **Ce qu'elle fait** : grille à colonnes fixes — heure en zone méta à gauche (largeur constante), équipes comme ancre de lecture, score/donnée chaude alignée à droite sur un axe vertical unique. Groupement par jour/compétition avec en-têtes collants, zéro variation de hauteur de ligne.
- **Pourquoi ça marche** : Gestalt (proximité + alignement) : l'œil scanne une seule colonne verticale par information ; la position fixe remplace la lecture.
- **Source** : https://www.fotmob.com/ · https://www.tikitaka.gg/best-football-apps

### Tables financières / enterprise (signal de changement)
- **Ce qu'elle fait** : combinaison **delta persistant** (ancien → nouveau, ou flèche + valeur) et badge de statut scannable en colonne dédiée — le flash temporaire n'est utilisé que pour le live, jamais comme seule trace.
- **Pourquoi ça marche** : règle métier paris : montrer *quoi* a changé, pas juste *que* ça a changé ; un signal qui doit survivre à un rechargement de page doit être un état, pas une animation.
- **Source** : https://www.pencilandpaper.io/articles/ux-pattern-analysis-enterprise-data-tables · https://www.uiprep.com/blog/the-ultimate-guide-to-designing-data-tables

### Winamax (bet slip cible)
- **Ce qu'elle fait** : ordre canonique du ticket : **sélection** (gros) → marché + match (petit) → **cote** accolée à la sélection → **mise** (champ) → **gains éventuels**. Slip stable quand les cotes bougent.
- **Pourquoi ça marche** : loi de Jakob — reproduire l'ordre exact de l'app de destination transforme la recopie en correspondance position-à-position, pas en re-parsing.
- **Source** : https://altenar.com/blog/how-to-design-a-sportsbook-user-experience-ux-that-wins-in-live-play/ · https://limeup.io/blog/betting-website-design/

## On adopte
- **Ligne en 4 zones fixes** : méta (heure mono + J/groupe, largeur fixe, gauche) → équipes + drapeaux (ancre, fr-1) → bloc données aligné droite (chip prono · pastille A–E · barre 1N2, chacun sur son axe vertical) → checkbox « Saisi » collée au bord droit. Fitts : cible de saisie toujours à la même position x, atteignable en série.
- **Changement = état, pas animation** : badge « modifié » + delta `1-0 → 2-1` dans la ligne, persistant jusqu'à acquittement (la coche « Saisi » acquitte), **plus compteur « N modifiés » dans l'en-tête** — l'exhaustivité se vérifie en un chiffre, pas en scrollant.
- **Progression façon courrier lu/non-lu** : ligne cochée = atténuée (opacité/encre réduite) mais **reste à sa place chronologique** ; compteur « x/y saisis » par en-tête de jour. La prochaine ligne non-atténuée est toujours la prochaine tâche : pas de todo-list séparée.
- **Carte de pari = miroir du slip Winamax** : sélection en premier et en gras, `@ cote` accolée, mise quart-Kelly en mono gros corps, retour si gagné en dernier ; modèle/ajusté/marché relégués en second niveau (détail), car non recopiés. Tous les chiffres à transcrire en mono tabulaire.
- **Passés** : `Réel` avant `Prono`, mêmes axes que les chips de « Futurs » (cohérence inter-onglets = Jakob interne).

## On rejette
- **Point orange pulsant** — animation infinie sans information (quoi ? combien ?), invisible après reload mental, hostile `prefers-reduced-motion` (a11y).
- **Déplacer/masquer les lignes saisies** (style todo-app) — casse l'ordre chronologique et la mémoire spatiale, le geste 2 dépend de la séquence.
- **Tri/filtres riches** — outil mono-utilisateur à ordre naturel unique (chronologie) ; toute option ajoute de la charge cognitive sans geste servi.
- **Surlignage temporaire seul à l'update** — fonctionne en live, pas pour un outil consulté épisodiquement.

## Pièges connus
- Le collapse ligne→carte en étroit détruit la scannabilité colonne par colonne : préférer **supprimer des colonnes secondaires** (barre 1N2, méta) avant de casser la grille (NN/g mobile tables · LogRocket responsive tables).
- Scroll horizontal = dernier recours ; jamais sans colonne équipe figée.
- Trop de signaux à droite (chip + pastille + barre + checkbox) se cannibalisent : un seul élément a le droit d'être saillant en couleur par ligne — ici le badge « modifié ».
- Hauteurs de ligne variables (details dépliable) : le déplié ne doit jamais décaler les axes des lignes voisines.
- Zebra striping + surlignage d'état entrent en conflit : choisir l'un.
