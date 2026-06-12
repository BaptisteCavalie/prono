# Pattern : Suivi de paris — ledger + bilan P&L/ROI neutre

> Date : 2026-06-12 · Contexte d'origine : feature "suivi paris + P&L" (prono WC2026)
> Note : pattern-researcher indisponible (limite de session) ; brief dérivé des
> patterns projet existants (recap-justesse, liste-matchs-dense) + contraintes
> domaine (paris-sportifs / ANJ) déjà actées dans `design/da.md`.

## Le problème
Montrer à un parieur solo, à côté des recommandations avant-match, le suivi de
ses paris réels (terminés + en cours) et un bilan cumulé tournoi (mise, gain net,
ROI), sans jamais valoriser le gain ni dramatiser la perte (cadre ANJ), et sans
confondre ce bilan « argent réel » avec le récap « justesse des pronos » (1N2)
déjà présent ailleurs. HTML/CSS Python stdlib, desktop, zéro JS de charting.

## Références (3 max)
### Journaux de paris / bankroll trackers (catégorie)
- **Ce qu'ils font** : un tableau-grand-livre une-ligne-par-pari (sélection, cote,
  mise, statut, gain net) + un en-tête de KPIs (P&L, ROI, win-rate).
- **Pourquoi ça marche** : le ledger dense est scannable et aligne les nombres ;
  les KPIs en tête répondent « où j'en suis » sans scroller. (design-judgment :
  hiérarchie — verdict d'abord, détail ensuite.)
- **Source** : convention établie (ex. trackers type "betting bankroll spreadsheet").

### Fintech / courtage — P&L signé sobre
- **Ce qu'elle fait** : un P&L affiché avec signe en chiffre mono, sans rouge
  alarmant ni vert récompense ; la couleur, si présente, reste discrète.
- **Pourquoi ça marche** : le signe (+/−) porte l'info ; traiter gain et perte à
  l'identique évite la charge émotionnelle (impératif ANJ : aucune incitation).
- **Source** : conventions tableaux de portefeuille (neutralité du signe).

### Pattern projet `recap-justesse-pronos`
- **Ce qu'il fait** : bilan cumulé tournoi en double encodage, hors rôles couleur
  réservés, avec N visible.
- **Pourquoi ça marche** : même besoin de bilan honnête ; on en reprend la
  rigueur (double encodage, neutralité) MAIS une forme différente (grille de
  métriques + table, pas la barre segmentée) pour ne pas confondre les deux.
- **Source** : `patterns/recap-justesse-pronos.md`.

## On adopte
- **Ledger une-ligne-par-pari** (table dense) : Pari (libellé + sélection) · Cote ·
  Mise · Statut · Net. Couvre simple ET combiné — un combiné = une ligne unique
  (tag `combiné`, cote combinée, statut), jamais de détail par sélection.
- **Bilan en grille de métriques** (`pnl-cell`) avec Gain net (P&L) et ROI en
  tête (`lead`), puis Mise totale et compteurs gagnés/perdus. Mono tabulaire.
- **Forme distincte du récap justesse** : grille + table ici, barre segmentée
  là-bas. Titre « Suivi des paris » / « Justesse des pronos » + note explicite
  « bilan argent réel, distinct ».
- **Statuts en chips neutres, double encodés** : Gagné (teal-soft = couleur
  *donnée* du projet, pas un vert succès) · Perdu (gris ardoise) · Remboursé
  (gris pointillé) · En cours (contour pointillé). Le label texte porte le sens.
- **Net présenté à l'identique quel que soit le signe** : même couleur (encre)
  pour + et − ; signe omis si zéro (remboursé → `0,00 €`, pas `+0,00 €`).
- **Paris en cours comptés à part** (jamais dans mise/P&L/ROI) ; Net = `—`.
- **État vide explicite** qui renvoie au flux ask-Claude (donnée écrite hors UI).
- **ROI = None si aucune mise** → afficher `—`, jamais une division par zéro.

## On rejette
- **Bankroll évolutive** (solde de départ + courant) — décision Baptiste : P&L +
  ROI suffisent, pas de solde à tenir à jour.
- **Rouge perte / vert gain** — rôles ok/warn/alert réservés ; et surtout
  dramatiserait la perte / valoriserait le gain (anti-ANJ).
- **Réutiliser la barre segmentée du récap justesse** — créerait deux bilans
  cumulés visuellement jumeaux mais sémantiquement distincts (argent vs 1N2).
- **Détail par sélection d'un combiné** — une ligne, un règlement ; le détail
  n'apporte rien au suivi.
- **Saisie/édition dans l'UI** — la donnée vient de la couche ask-Claude.

## Pièges connus
- **Net d'un gagnant** = mise × (cote − 1), PAS mise × cote (la mise revient mais
  n'est pas un gain). Erreur classique qui gonfle le P&L.
- **ROI sur mise vs sur bankroll** : ici ROI = P&L / mise totale engagée (pas un
  capital). Le dire pour éviter l'ambiguïté.
- **Division par zéro** sur ROI quand aucun pari réglé.
- **`+0,00 €`** pour un remboursé : laid et trompeur — omettre le signe à zéro.
- **Confusion des deux bilans** : sans titres + emplacement distincts, l'œil les
  fond ; garder formes visuelles différentes.
- **Fichier `data/bets.json` cassé** : tolérer (liste vide), ne jamais planter
  la page Paris.
