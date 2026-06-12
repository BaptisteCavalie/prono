# Pattern : Châssis dashboard — sidebar persistante + repli des passés + filtre instantané
> Date : 2026-06-12 · Contexte d'origine : refonte dashboard prono (sidebar + repli passés + filtre pays)

## Le problème
Un outil mono-utilisateur desktop a besoin d'un châssis qui se fait oublier : une sidebar à 3 entrées qui repère sans dominer, une page Matchs qui masque le passé par défaut pour scanner les à-venir sans scroll, et un filtre pays instantané qui réduit la liste sans jamais perdre l'utilisateur. Le châssis doit dégrader proprement sans JS (server-rendered) et garder sa lisibilité d'état actif au clavier.

## Références (3 max)

### Linear / Vercel / Notion (sidebar persistante atténuée)
- **Ce qu'elle fait** : sidebar fixe, toujours visible, peu d'entrées ; état actif = **fond d'item teinté + texte renforcé** (pas un simple gras), largeur ~220-256px. Châssis atténué pour pousser le contenu au premier plan ; frontière nette, pas de bordure-vedette.
- **Pourquoi ça marche** : visibilité du statut système + loi de proximité — 3 entrées ne demandent ni groupes ni icônes-seules ; l'actif combine **deux** signaux redondants (fond + encre) pour ne pas dépendre de la couleur seule (a11y).
- **Source** : https://linear.app/now/behind-the-latest-design-refresh · https://designsystem.digital.gov/components/side-navigation/

### NN/g + Inclusive Components (disclosure « passés »)
- **Ce qu'elle fait** : section repliable = **disclosure** (en-tête cliquable révèle/masque), distincte d'un accordéon. Défaut = replié pour ce qui est consulté rarement. L'en-tête porte un **résumé/teaser** quand c'est replié.
- **Pourquoi ça marche** : progressive disclosure — réduit charge et scroll sans cacher l'accès ; `aria-expanded` garantit que le repli est perçu au clavier et lecteur d'écran.
- **Source** : https://www.nngroup.com/articles/accordions-on-desktop/ · https://inclusive-components.design/collapsible-sections/

### Pencil & Paper — enterprise filtering (filtre texte instantané)
- **Ce qu'elle fait** : filtrage **instantané** (réduit à la frappe, pas de bouton), feedback du nombre de résultats près de l'input, « aucun résultat » = état explicite avec sortie (effacer). Champ **au-dessus de la liste** qu'il gouverne.
- **Pourquoi ça marche** : feedback immédiat pour action à faible enjeu sur petite liste ; afficher le compte évite le « 0 » incompris ; sortie toujours visible = pas de cul-de-sac.
- **Source** : https://www.pencilandpaper.io/articles/ux-pattern-analysis-enterprise-filtering

## On adopte
- **Sidebar = `<nav><ul>` server-rendered, 3 `<a href>` réels** (par param d'URL) : marche sans JS, actif calculé serveur. Item actif = `aria-current="page"` **+** fond teinté + encre renforcée (teal lumineux sur sombre, deux signaux), focus clavier visible. Pas d'icônes-seules ni de mode collapsé : 3 libellés texte.
- **Passés = disclosure replié par défaut.** En-tête = vrai `<button aria-expanded>`, contenu en `hidden`/`<details>` qui suit en source order. **Libellé chiffré** : « Matchs passés (12) » (le compte = teaser replié). Dégradation sans JS. Transition ≤ 200 ms, respecte `prefers-reduced-motion`.
- **Filtre pays = un `<input type="search">` au-dessus de la liste**, dans le canvas clair (JAMAIS dans la sidebar sombre). À la frappe : masquer les lignes hors-match, **compte vivant** (« 7 matchs · pays = … »), `aria-live="polite"`. État « aucun résultat » = message + bouton « Effacer ».
- **Filtre × repli — règle d'or** : filtre actif → les en-têtes de section dont toutes les lignes sont masquées disparaissent (pas de « Passés (0) » trompeur), et une section repliée contenant un match correspondant **se déplie auto** ou affiche son compte filtré. Effacer le filtre restaure l'état de repli.
- **Persistance du repli** : localStorage entre visites, mais **défaut = replié** au premier rendu serveur (sans-JS et première charge corrects).

## On rejette
- **Icônes-seules / sidebar collapsible** — pertinent à 15 entrées, pas à 3 (anti-modèle « cockpit NASA »).
- **État actif par couleur seule** — invisible daltonisme/clavier ; on double (fond + encre + `aria-current`).
- **Filtre dans la sidebar** — mélange nav sombre et donnée claire ; casse « le sombre s'arrête à la nav ».
- **Bouton « Appliquer »** — enjeu faible, petite liste : instantané attendu.
- **Accordéon exclusif** — Futurs et Passés sont deux disclosures indépendantes.
- **Masquer le passé sans compte ni accès** — fait douter que la donnée existe.

## Pièges connus
- `aria-controls` quasi-inutile : suffit que le contenu suive le bouton en source order.
- `aria-expanded` vit sur le **bouton**, synchronisé avec `hidden`/`open`.
- **Filtre qui vide une section repliée** = piège n°1 : un match caché derrière « Passés » replié paraît absent → auto-dépli ou compte filtré.
- En-tête à 0 résultat laissé visible pendant un filtre = bruit trompeur ; le masquer.
- **Focus perdu** après filtrage/repli : ne pas retirer du DOM l'élément focusé sans replacer le focus ; masquer via `hidden`, garder le champ de filtre focusé.
- `aria-current="page"` reflète la vraie page server-rendered, pas un état JS.
- `prefers-reduced-motion` : transition de repli à 0.
- Persistance localStorage **sans** fallback : le défaut serveur (replié) doit rester cohérent sans JS.
