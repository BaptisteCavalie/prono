# Pattern : Récap justesse — barre segmentée + compteurs, jamais un score de certitude
> Date : 2026-06-12 · Contexte d'origine : feature "scores réels + récap justesse pronos" (prono WC2026)

## Le problème
Sur un ensemble de matchs terminés, montrer d'un coup d'œil la répartition des pronos en 3 catégories (exact / bon résultat / erreur) sans que ce résumé se lise comme une "note de fiabilité" du modèle, et sans mentir sur un petit échantillon (premiers jours = 2-3 matchs). Le tout en HTML/CSS Python stdlib, sans JS de charts ni webfont.

## Références (3 max)

### BBC — tableaux de football (forme des 5 derniers)
- **Ce qu'elle fait** : affiche la forme par pastilles W/D/L. Après refonte accessibilité : lettre + couleur (W vert, L rouge, D gris), pastilles passées de 11×4 px à 36×36 px.
- **Pourquoi ça marche** : double encodage (forme/lettre + couleur), jamais la couleur seule — exactement le besoin ici, où la palette ok/warn/alert et la gamme A–E sont déjà réservées. Le caractère porte le sens, la couleur ne fait que renforcer.
- **Source** : https://wearecolorblind.com/examples/bbc-online-football-tables/

### FiveThirtyEight — "Checking Our Work" / calibration
- **Ce qu'elle fait** : évalue ses propres prévisions par calibration (les "70 %" arrivent ~70 % du temps) et Brier score, présentés comme un bilan honnête variable selon l'année et le sport, jamais comme un palmarès de bonnes réponses.
- **Pourquoi ça marche** : pose le principe directeur — une sortie probabiliste se juge sur la calibration agrégée, pas au match près. Un prono "raté" sur un favori n'est pas une faute si la proba était correcte. Cadre la copie : le récap est un comptage descriptif, pas un score de qualité du modèle.
- **Source** : https://projects.fivethirtyeight.com/checking-our-work/ · https://en.wikipedia.org/wiki/Brier_score

### Corpus best-practice data-viz — pie vs barre empilée pour petites parts
- **Ce qu'elle fait** : recommande la barre empilée plutôt que le camembert dès qu'il faut comparer des parts ou en lire de petites — l'œil estime mieux des longueurs que des angles/aires.
- **Pourquoi ça marche** : 3 catégories dont une potentiellement minuscule (1 exact sur 3) = le pire cas du camembert (angle aigu illisible). La barre horizontale empilée garde la lecture part-du-tout sans le coût de précision.
- **Source** : https://www.atlassian.com/data/charts/how-to-choose-pie-chart-vs-bar-chart · https://inforiver.com/insights/11-pie-chart-alternatives-and-when-to-use-them/

## On adopte
- **Barre horizontale segmentée 100 %** (un seul conteneur flex, largeurs en %), pas de donut. Ordre fixe gauche→droite : exact · bon · erreur. CSS pur, lisible mobile, alignée sur la densité "ligne" de l'app.
- **Triade de compteurs en mono tabulaire** : `3 exacts · 5 bons · 2 erreurs` — les chiffres bruts portent l'info, la barre n'est qu'un appui visuel.
- **Échantillon toujours affiché en clair** : `sur 10 matchs terminés`. Le N est dans la phrase, pas en infobulle. Antidote petit-échantillon n°1.
- **Encodage propre, hors rôles réservés** : 3 teintes dérivées de l'accent teal (teal plein = exact, teal désaturé/clair = bon, gris-encre = erreur), JAMAIS vert/orange/rouge (réservés ok/warn/alert) ni la gamme A–E. **Double encodage** : chaque segment et chaque compteur porte son label texte ; la couleur ne décide jamais seule.
- **Garde-fou petit N** : sous un seuil (< 5 matchs), compléter par une phrase comptée (`2 exacts, 1 bon sur 3 matchs — trop tôt pour conclure`) et atténuer la barre.
- **Cadrage sémantique** : titre neutre "Justesse des pronos" + micro-note "comptage descriptif, pas une note de fiabilité du modèle". Aucun pourcentage agrégé géant.

## On rejette
- **Donut / pie en conic-gradient** — 3 parts dont une petite = angles illisibles, et a11y coûteuse pour zéro gain sur une barre.
- **Pourcentage de réussite unique mis en avant** ("82 %") — se lit comme un score de certitude, interdit par le brief (sortie = distribution calibrée).
- **Couleurs ok/warn/alert ou notes A–E** pour les 3 parts — rôles réservés ailleurs ; créerait une fausse hiérarchie "vert = bien / rouge = mal".
- **Masquer le N derrière un % ou un hover** — l'honnêteté petit échantillon exige le volume visible sans interaction.

## Pièges connus
- **Pie chart à 3 parts** : la part minoritaire devient un angle aigu impossible à comparer ; préférer la longueur.
- **Couleur seule** : sans label texte, inaccessible et confondue avec les signaux ok/warn. Double encodage systématique.
- **Confusion "justesse" ↔ "qualité du modèle"** : un bon modèle probabiliste a des erreurs attendues.
- **Petit N early-season** : une barre sur n=2 dramatise du bruit ; seuil minimum + bascule texte.
- **Arrondis** : 3 segments en % qui ne somment pas à 100 ; donner le dernier segment en reste (100 − a − b) pour éviter le filet blanc en bout de barre.
