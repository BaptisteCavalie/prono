# Paris sportifs & prédiction football

> Bootstrappé le 2026-06-10 · Projets sources : prono (prédicteur WC2026)
> Statut : **draft — à valider par Baptiste**

Ce qui n'est PAS générique ici : un pronostic est une **distribution de
probabilités**, jamais une certitude — et le produit ment dès qu'il l'affiche
comme telle. La valeur ne vient pas de « prédire le bon score » mais d'être
mieux calibré que le marché après retrait de sa marge. Et c'est un domaine
**régulé** (ANJ) où pousser à parier est un risque légal, pas seulement éthique.

## Confiance & attentes utilisateurs

- La confiance vient de la **calibration honnête**, pas de la confiance affichée.
  Un modèle qui dit « 62 % » doit gagner ~62 % du temps sur ces cas. Mieux vaut
  un « 38 % » lucide qu'un « prono sûr » faux.
- **Toujours montrer l'incertitude.** Une proba 1N2, une fourchette, jamais un
  score sec présenté comme LA prédiction (cf. pièges).
- **Transparence du modèle** : dire d'où sort le chiffre (Elo, forme, xG, prior
  expert) augmente la confiance. Une boîte noire qui affiche « 3-1 » n'en inspire
  aucune.
- **Jamais inciter à parier.** Pas de « pari du jour à ne pas manquer », pas de
  compteur de gains potentiels clignotant. Le produit informe, l'utilisateur
  décide. C'est l'équivalent ici du « no dark pattern » fintech — et c'est cadré
  par l'ANJ.

## Contraintes réglementaires & légales (France — ANJ)

- **Message d'avertissement obligatoire**, visible : « Jouer comporte des risques :
  endettement, isolement, dépendance. Pour être aidé, appelez le 09 74 75 13 13
  (appel non surtaxé). » + **interdit aux mineurs (18+)**.
- Un outil de **pronostic/aide à la décision n'est pas un opérateur agréé** :
  il ne prend pas de mises, ne tient pas de compte joueur. Mais dès qu'il
  **recommande une mise** (sélection + stake), il glisse vers le conseil : porter
  l'avertissement responsable et ne jamais garantir un gain.
- Pas de ciblage des mineurs ni des publics vulnérables ; pas de promesse de
  « système gagnant ».

## Données sensibles & affichage

- **Cote → probabilité implicite** : `p_implicite = 1 / cote`, mais la somme des
  `1/cote` d'un marché dépasse 100 % — c'est le **vig / overround** (marge du
  bookmaker). **Toujours normaliser** avant de comparer au modèle ; afficher du
  `1/cote` brut comme « probabilité » est faux.
- **Value** = `p_modèle > p_implicite` (après retrait du vig). C'est le seul motif
  légitime de pari. EV = `p_modèle × cote − 1`.
- **Mise** : Kelly fractionné (jamais Kelly plein), plafonnée par la bankroll.
  Une mise ne dépasse jamais la bankroll ; afficher la bankroll restante.
- `tabular-nums` sur toutes les cotes, probas, mises, gains qui s'empilent.
- Probabilités 1N2 affichées **sommant à 100 %** ; format local fr (`62 %`,
  `1,40` pour les cotes décimales, espace insécable).
- Le **score pronostiqué** est le mode d'une distribution (Poisson/Dixon-Coles) :
  l'afficher **avec sa probabilité** (« 2-1, p≈11 % »), jamais nu.

## Conventions sectorielles (loi de Jakob)

- Notation **1N2 / 1X2** (domicile / nul / extérieur) ; **cotes décimales** en
  France/Europe (pas américaines ni fractionnaires). « Cote », « mise »,
  « gain potentiel = mise × cote ».
- **Combiné** : les cotes se multiplient, les probabilités aussi (le risque
  explose) — le dire.
- Ligne de match : **domicile à gauche, extérieur à droite**, drapeaux nationaux
  (drapeau du pays, pas d'union politique : Angleterre ≠ Union Jack).
- Heures en **Europe/Paris** pour un public français.

## Erreurs & cas limites critiques du métier

- **Pas de cote / pas de marché** : afficher le pronostic modèle seul, sans value
  ni mise (on ne calcule pas de value sans référence marché).
- **Équipe sans historique** (nation fraîchement qualifiée, données creuses) :
  signaler la faible fiabilité plutôt que sortir un chiffre faussement précis.
- **Match reporté / annulé, carton rouge, blessure de dernière minute** : la
  prédiction pré-match devient caduque — gérer la dérive **pré-match vs live**.
- **Mise > bankroll**, **EV négatif** : refuser / avertir, ne pas proposer le pari.
- Backtest : se méfier du **survivorship** et du look-ahead (utiliser les cotes
  de clôture/ouverture cohérentes avec l'instant de décision).

## Pièges connus

- Prendre `1/cote` pour la vraie probabilité (**ignorer le vig**) → fausse value.
- Présenter le score le plus probable comme « la prédiction » sans sa proba
  (souvent <15 %) → surconfiance, le piège n°1 du domaine.
- Confondre **précision** (taux de bons pronos) et **calibration** (Brier / RPS) :
  c'est la calibration qui fait un bon prédicteur, pas le hit-rate.
- Sophisme du joueur / biais de récence dans la copy (« invaincu depuis 5
  matchs donc va gagner »).
- Kelly plein → ruine sur la variance ; toujours fractionné.

## Règles ajoutées par /retro

<!-- Amendements validés, datés -->
