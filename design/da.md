# DA — prono (WC 2026)

> Date : 2026-06-11 · Révisé 2026-06-12 (passage dashboard) · Validé par
> Baptiste · S'amende via /retro

## Territoire
Outil mono-utilisateur : Baptiste, seul, avant les matchs — analytique, pressé,
**sur desktop** (le mobile n'est plus une cible). Trois gestes à servir :
**scanner les matchs à venir d'un coup d'œil** (passés repliés par défaut, pas
de scroll inutile), **filtrer par pays**, **reporter dans MPP / lire un pari
prêt à saisir** dans Winamax. L'outil prend la forme d'un **dashboard à menu
latéral** : une sidebar sombre sert de **châssis** (navigation Matchs · Paris ·
Diagnostics), le **contenu reste sur un canvas papier clair**. La culture
visuelle des bookmakers (sombre, promo, urgence) reste l'anti-modèle — d'où la
règle cardinale : **le sombre s'arrête à la navigation, jamais sur la donnée de
pari**. On se range du côté du data-journalism + de l'instrument pro.

**Ambiance** : calibré · dense · poste de pilotage
**Anti-mots** : « bookmaker » (urgence, promo, clignotant), « admin template
générique » (corporate Bootstrap), « dark mode racoleur »

## Références (3 max)
### Linear — refonte 2024/2025 (sidebar atténuée)
- **Source** : https://linear.app/now/behind-the-latest-design-refresh (requête : « Linear dark sidebar light content workspace redesign »)
- **Capture** : non sauvegardée (app authentifiée ; og:image marketing générique)
- **On vole** : le châssis sombre **atténué** qui fait passer le contenu au
  premier plan ; le virage vers un gris **chaud** (pas bleu froid) ; un seul
  accent ; la densité de navigation maîtrisée (3 entrées, pas 15).
- **On laisse** : le dark mode sur TOUT le contenu (notre canvas reste clair),
  l'esthétique dev/keyboard-first, le glass.

### FiveThirtyEight — World Cup forecast
- **Source** : https://projects.fivethirtyeight.com/ (requête : « FiveThirtyEight World Cup forecast probability table »)
- **Capture** : non sauvegardée (site démantelé)
- **On vole** : la probabilité comme objet premier — 1N2 partout, jamais un
  score sec ; tables denses scannables ; mono tabulaire ; des neutres + un signal.
- **On laisse** : l'appareil éditorial (articles, bracket Monte-Carlo).

### Yuka
- **Source** : https://yuka.io (requête : « Yuka app nutri-score design »)
- **Capture** : `design/references/yuka-grades-preview.png`
- **On vole** : le verdict instantané (note + couleur) suivi de sa décomposition
  par facteurs — le pattern exact du Nutri-prono.
- **On laisse** : le ton grand public et les illustrations.

## Typographie
- **Police** : stack système `system-ui` (400/600/700) — robustesse assumée :
  outil local/offline en pure stdlib, zéro dépendance réseau.
- **Mono** : `ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas` +
  `font-variant-numeric: tabular-nums` — sur TOUS les chiffres (probas, scores,
  cotes, mises, Elo). Le geste Decima Mono de FiveThirtyEight, sans webfont.
- **Chargement** : aucun (stacks système).

## Couleur — deux zones
Le dashboard a deux territoires chromatiques distincts, et c'est délibéré.

### Canvas (contenu) — inchangé
- **Température** : chaud clair — papier crème `#f6f4ec`, surfaces ivoire.
- **Accent** : teal `#0f5c78` — signale la donnée et la navigation, jamais une
  incitation à parier.
- **Neutres** : encre `#1f2430`, secondaire `#5d6679` ; bordures froides
  discrètes (`#d8deea`).
- **Sémantique** : ok/warn/alert réservés aux signaux ; la gamme Nutri A–E est
  RÉSERVÉE aux verdicts de pari — jamais décorative ; la rampe récap
  (`--recap-exact/bon/erreur`) réservée à la justesse des pronos.

### Sidebar (châssis) — nouveau
- **Surface** : sombre **chaude** `~#1d2330` (dérivée de l'encre `#1f2430`, ni
  noir pur ni bleu froid) ; item au survol légèrement plus clair.
- **Texte** : clair `~#c7cedd` (atténué), `~#f4f6fb` pour l'actif/titre.
- **Actif** : le teal `#0f5c78` est illisible sur sombre → l'état actif =
  **fond d'item teinté** `#143b4b` + **encre teal lumineux** `#86d4ec` (double
  encodage, sans barre d'accent à gauche — interdit anti-slop) ; contrastes
  validés au build (texte actif 7.2:1, texte nav 9.63:1).
- **Frontière** : sidebar/canvas séparés par un trait net 1px, pas une ombre.

## Densité & forme
- **Densité** : dense — consultation rapide pré-match ; une ligne = un match,
  ordre chronologique, passés masquables.
- **Layout** : sidebar fixe ~220 px à gauche, canvas fluide à droite.
- **Radius** : doux — 12-14px cards/panels du canvas, 8px items de nav,
  pilules (999) pour chips de score et mises.
- **Élévation** : plate — bordures 1px, pas d'ombres (réservées aux flottants).

## Motion
Fonctionnelle uniquement. Le « prono modifié » est un **état** persistant
(badge + delta), pas une animation. Le repli des passés est un état (mémorisé),
sa transition reste ≤ 200 ms et respecte `prefers-reduced-motion`.

## L'élément signature
Le **verdict Nutri-prono** — la pastille A–E qui note chaque pari, empruntée à
l'étiquetage alimentaire. Reconnaissable logo masqué. Intouchable. Le nouveau
parti-pris de forme (canvas clair **encadré par un châssis sombre**) le met en
scène sans le concurrencer : un cockpit de pronos, ni bookmaker, ni admin.

## On rejette
- **Le dark mode sur la donnée de pari** — le sombre s'arrête à la nav ; le
  contenu calme, clair, honnête. L'urgence sombre est un dark pattern du domaine
  (cadre ANJ, cf. domain-knowledge paris-sportifs).
- **L'admin template générique** — sidebar à 15 icônes, corporate Bootstrap.
  Trois entrées, pas un cockpit NASA.
- **Les webfonts** — offline d'abord.
- **Le score sec présenté comme LA prédiction** — toujours la distribution 1N2
  visible (calibration honnête).
