---
name: design-judgment
description: Principes de design à appliquer SYSTÉMATIQUEMENT avant de créer ou modifier toute UI — composant, page, layout, formulaire, navigation, landing, dashboard, email. Déclencher dès que la tâche touche au visuel ou à l'expérience, même si l'utilisateur ne dit pas "design" — y compris sur "ajoute un bouton", "fais une page", "améliore cet écran", "refais le formulaire".
---

# Design Judgment

Charge ce skill AVANT d'écrire le premier composant, pas après. Ces principes
guident les décisions ; en cas de doute, ils tranchent.

## Hiérarchie d'abord

Toute interface se conçoit dans cet ordre : (1) quelle est l'action principale
de l'écran, (2) quelles informations la soutiennent, (3) tout le reste recule.
- Une seule action primaire par écran. Les actions secondaires sont visuellement
  secondaires (ghost, lien), pas des boutons pleins concurrents.
- La hiérarchie se construit par taille, graisse et espacement — la couleur
  vient en dernier, comme signal, jamais comme béquille.
- Commencer en niveaux de gris, ajouter la couleur d'accent à la fin, uniquement
  là où elle dirige l'attention. (Réf : Refactoring UI, Wathan & Schoger.)

## Gestalt appliqué

- **Proximité** : l'espacement code la relation. Espace intra-groupe < espace
  inter-groupes, toujours. Un label est plus proche de SON champ que du champ
  précédent.
- **Similarité** : les éléments de même fonction ont la même forme. Deux styles
  de bouton = deux significations, pas deux humeurs.
- **Continuité / alignement** : tout élément s'aligne sur quelque chose. Une
  grille perceptible, des bords qui se répondent. Le désalignement est un
  message — n'en envoie pas par accident.

## Lois UX opérationnelles (lawsofux.com)

- **Fitts** : les cibles fréquentes sont grandes et proches. Cibles tactiles
  ≥ 44px. L'action destructive est ÉLOIGNÉE de l'action fréquente.
- **Hick** : chaque option ajoutée ralentit la décision. Réduire les choix
  visibles ; le reste derrière un "plus d'options".
- **Jakob** : les utilisateurs passent leur vie ailleurs. Suivre les conventions
  (position du panier, comportement des liens, iconographie standard) sauf
  raison forte documentée.
- **Miller / charge cognitive** : chunker. Formulaires longs → étapes. Données
  denses → groupes titrés. Numéros longs → segmentés (IBAN par blocs de 4).
- **Pic-fin (peak-end)** : soigner le moment de réussite (confirmation,
  empty state rempli) et la fin du flow — c'est ce qui reste.

## Typographie

- 2 graisses max par écran, 3 niveaux de taille suffisent à 95% des écrans.
- Texte courant : 16px minimum, interligne 1.5, lignes ≤ 75 caractères.
- Hiérarchiser par la taille ET la graisse ensemble, jamais par la couleur seule.
- Les chiffres importants (montants, stats) : grands, tabular-nums, sans fioritures.

## Espacement

- Système 4/8 strict (tokens). En cas de doute entre deux espacements : le plus grand.
- L'espace blanc n'est pas du vide à remplir, c'est l'outil de hiérarchie le
  moins cher. Un écran "vide" qui respire bat un écran "riche" illisible.

## États — non négociable

Concevoir les 5 états AVANT l'état idéal parfait :
1. **Empty** — guide vers la première action, jamais juste "Aucune donnée".
2. **Loading** — skeleton qui préfigure le layout (pas de spinner plein écran).
3. **Error** — dit quoi faire, propose une issue (retry, support).
4. **Partial** — peu de données : l'écran doit rester digne avec 1 seul item.
5. **Ideal** — celui qu'on maquette toujours et qui est le plus rare en prod.

## Processus de décision en cas de doute

1. Que dit le pattern brief / la pattern library ?
2. Que dit la convention (loi de Jakob) ?
3. Quelle option a le moins d'éléments ?
Si les trois divergent : choisir le plus simple et noter l'arbitrage au rapport.
