# DA — prono (WC 2026)

> Date : 2026-06-11 · Validé par Baptiste le 2026-06-11 · S'amende via /retro

## Territoire
Outil mono-utilisateur : Baptiste, seul, avant les matchs — analytique, pressé.
Trois gestes à servir avant tout : **repérer un prono qui a changé** après
update des data, **suivre l'ordre chronologique** pour reporter les pronos
dans MPP, **lire un pari prêt à saisir** dans Winamax. La culture visuelle des
bookmakers (sombre, promo, urgence) est l'anti-modèle ; on se range du côté
du data-journalism. La lisibilité prime sur tout effet.

**Ambiance** : calibré · dense · papier
**Anti-mots** : « bookmaker » (urgence, promo, clignotant), « magie IA », « dashboard corporate »

## Références (3 max)
### FiveThirtyEight — 2022 World Cup forecast
- **Source** : https://projects.fivethirtyeight.com/2022-world-cup-predictions/ (requête : « FiveThirtyEight World Cup forecast probability table »)
- **Capture** : non sauvegardée (site démantelé, og:image générique ABC News)
- **On vole** : la probabilité comme objet premier — 1N2 partout, jamais un score sec ; tables denses scannables ; des neutres + un signal.
- **On laisse** : l'appareil éditorial (articles, bracket Monte-Carlo) — prono est un outil de travail, pas une publication.

### Yuka
- **Source** : https://yuka.io (requête : « Yuka app nutri-score design »)
- **Capture** : `design/references/yuka-grades-preview.png`
- **On vole** : le verdict instantané (note + couleur) suivi de sa décomposition par facteurs — le pattern exact du Nutri-prono et du détail forme/blessures/news.
- **On laisse** : le ton grand public et les illustrations — un seul utilisateur, expert.

### FotMob
- **Source** : https://www.fotmob.com (requête : « FotMob match day design ») — voir l'app mobile, onglet Matches
- **Capture** : non sauvegardée (og:image = logo seul)
- **On vole** : la densité match-day sur mobile, fond clair, un seul accent, le contenu comme seule focale.
- **On laisse** : l'accent vert et le look « app store » générique.

## Typographie
- **Police** : stack système `system-ui` (400/600/700) — choix de robustesse
  assumé : outil local/offline en pure stdlib, zéro dépendance réseau. Pas un
  défaut subi : la personnalité typographique vient du mono.
- **Mono** : `ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas` +
  `font-variant-numeric: tabular-nums` — sur TOUS les chiffres (probas,
  scores, cotes, mises, Elo). Le geste Decima Mono de FiveThirtyEight, sans
  webfont.
- **Chargement** : aucun (stacks système).

## Couleur
- **Température** : chaud clair — papier crème `#f6f4ec`, surfaces ivoire.
  Distancie immédiatement des bookmakers sombres.
- **Accent** : teal `#0f5c78` — signale la donnée et la navigation, jamais
  une incitation à parier.
- **Neutres** : encre `#1f2430`, secondaire `#5d6679` ; bordures froides
  discrètes (`#d8deea`).
- **Sémantique** : ok/warn/alert réservés aux signaux (warn = « prono
  changé ») ; la gamme Nutri A–E est RÉSERVÉE aux verdicts de pari — jamais
  décorative.

## Densité & forme
- **Densité** : dense — consultation rapide pré-match ; une ligne = un match,
  ordre chronologique par défaut, le détail en dépliant.
- **Radius** : doux — 12-14px cards/panels, pilules (999) pour chips de score
  et mises.
- **Élévation** : plate — bordures 1px, pas d'ombres ; réservée aux
  flottants éventuels.

## Motion
Fonctionnelle uniquement — l'unique animation est le pulse du change-dot
(prono modifié par l'update des data) : c'est un signal de travail, pas un
décor. Rien d'autre ne bouge.

## L'élément signature
Le **verdict Nutri-prono** — la pastille A–E qui note chaque pari, empruntée
à l'étiquetage alimentaire. Reconnaissable logo masqué. Intouchable.

## On rejette
- Le dark mode bookmaker — l'outil doit calmer, pas exciter ; l'urgence est un dark pattern du domaine (cadre ANJ, cf. domain-knowledge paris-sportifs).
- Les webfonts — offline d'abord ; une police bloquante contre 200 ms de caractère, non.
- Le score sec présenté comme LA prédiction — toujours la distribution 1N2 visible (calibration honnête).
