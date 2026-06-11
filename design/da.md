# DA — prono (WC 2026)

> Date : 2026-06-11 · Validé par Baptiste le 2026-06-11 · Amendé le 2026-06-11
> (pivot forme : dashboard à menu latéral) · S'amende via /retro

## Territoire
Outil mono-utilisateur : Baptiste, seul, avant les matchs — analytique, pressé.
Trois gestes à servir avant tout : **repérer un prono qui a changé** après
update des data, **suivre l'ordre chronologique** pour reporter les pronos
dans MPP, **lire un pari prêt à saisir** dans Winamax. La culture visuelle des
bookmakers (sombre partout, promo, urgence) reste l'anti-modèle ; on se range
du côté du data-journalism, mais dans une **coquille d'outil de travail
structuré** — un vrai dashboard à navigation latérale, pas une page unique.
La lisibilité prime sur tout effet.

**Ambiance** : calibré · dense · structuré
**Anti-mots** : « SaaS générique sans âme » (chrome froid sans hiérarchie ni
caractère), « dark mode bookmaker » (urgence, promo, clignotant), « magie IA »

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
- **On vole** : la densité match-day, fond clair de la zone de contenu, un seul accent, le contenu comme seule focale.
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
- **Température** : chaud clair — la **zone de contenu** reste papier crème
  `#f6f4ec`, surfaces ivoire. C'est là que vit la donnée ; elle distancie
  immédiatement des bookmakers sombres.
- **Sidebar (chrome de navigation)** : zone **foncée et froide** assumée —
  teal-encre profond `#18242c`, item actif sur fond teal `#0f5c78`, libellés
  inactifs en gris-bleu clair `#c7d2dc`. Choix de Baptiste (2026-06-11) : un
  chrome d'outil pro qui pose la nav, tiré du teal de marque pour ne pas
  tomber dans le gris SaaS anonyme. La sidebar est la SEULE zone sombre ;
  ce n'est pas un dark mode (cf. « On rejette »).
- **Accent** : teal `#0f5c78` — signale la donnée et la navigation, jamais
  une incitation à parier.
- **Neutres** : encre `#1f2430`, secondaire `#5d6679` ; bordures froides
  discrètes (`#d8deea`).
- **Sémantique** : ok/warn/alert réservés aux signaux (warn = « prono
  changé ») ; la gamme Nutri A–E est RÉSERVÉE aux verdicts de pari — jamais
  décorative.

## Densité & forme
- **Layout** : **dashboard à coquille fixe** — menu latéral persistant à
  gauche (sections Futurs · Passés · Paris · Diagnostics), zone de contenu en
  panneaux/cartes à droite. Comme Linear / Stripe / Vercel : une sidebar fixe
  donne l'accès aux sections sans manger de hauteur verticale et monte en
  charge sans restructurer (requête : « fixed sidebar card content dashboard
  pattern », navbar.gallery / artofstyleframe). En tête de la zone de
  contenu : une **recherche unique** qui filtre les matchs de la section
  courante par nom de pays (préserve l'ordre chrono, ne réordonne rien).
- **Densité** : dense — consultation rapide pré-match ; une ligne = un match,
  ordre chronologique par défaut, le détail en dépliant.
- **Radius** : doux — 12-14px cards/panels, pilules (999) pour chips de score
  et mises.
- **Élévation** : plate — bordures 1px, pas d'ombres ; réservée aux
  flottants éventuels.
- **Responsive** : la sidebar se replie au-dessus du contenu en étroit
  (mobile) — la zone de contenu reste prioritaire, le geste match-day d'abord.

## Motion
Fonctionnelle uniquement — rien ne bouge. Le « prono modifié » est un état
persistant (badge avec delta ancien → nouveau), pas une animation : un signal
qui doit survivre au rechargement est un état. <!-- amendé 2026-06-11,
pattern liste-matchs-dense : remplace le pulse du change-dot -->

## L'élément signature
Le **verdict Nutri-prono** — la pastille A–E qui note chaque pari, empruntée
à l'étiquetage alimentaire. Reconnaissable logo masqué. Intouchable.

## On rejette
- **Le dark mode bookmaker généralisé** — l'outil doit calmer, pas exciter ;
  l'urgence est un dark pattern du domaine (cadre ANJ, cf. domain-knowledge
  paris-sportifs). La sidebar foncée est un chrome de navigation scopé, jamais
  une mise en scène d'urgence : la donnée et les paris vivent sur fond clair.
- Les webfonts — offline d'abord ; une police bloquante contre 200 ms de caractère, non.
- Le score sec présenté comme LA prédiction — toujours la distribution 1N2 visible (calibration honnête).
- Le chrome SaaS générique sans hiérarchie — la sidebar a du caractère (teal de marque, mono, densité), pas un gris d'usine.
