---
name: a11y
description: Checklist d'accessibilité WCAG 2.2 AA à appliquer pendant TOUT build d'UI et toute critique — formulaires, navigation, modales, composants interactifs, couleurs, images. Déclencher dès qu'on écrit du HTML/JSX, pas seulement quand l'utilisateur mentionne "accessibilité".
---

# Accessibilité — WCAG 2.2 AA opérationnel

AA est le plancher de la constitution. Cette checklist s'applique PENDANT le
build (concevoir accessible) puis se vérifie en gate (axe-core via le hook).
Référence complète : https://www.w3.org/WAI/WCAG22/quickref/

## Structure & sémantique

- HTML sémantique d'abord : `button` pour agir, `a` pour naviguer, `nav`,
  `main`, `header` — jamais de `div onClick`.
- Un seul `h1` par page, niveaux de titres sans saut (h2 → h3, pas h2 → h4).
- Les listes sont des `ul`/`ol`, les tableaux de données des `table` avec `th`.

## Clavier — le test le plus rentable

- TOUT ce qui est cliquable est atteignable et activable au clavier (Tab,
  Enter/Espace), dans un ordre logique.
- Focus TOUJOURS visible : outline ≥ 2px, contraste ≥ 3:1 avec le fond.
  `outline: none` sans remplacement = blocker.
- Modale : focus piégé dedans, Échap ferme, focus rendu au déclencheur.
- Pas de piège : on peut toujours sortir d'un composant au clavier.

## Couleur & contraste

- Texte courant ≥ 4.5:1 ; grand texte (≥24px ou 19px gras) ≥ 3:1 ;
  composants UI et bordures de champs ≥ 3:1.
- L'information n'est JAMAIS portée par la couleur seule : erreur = couleur
  + icône + texte ; lien dans un paragraphe = souligné.

## Formulaires

- Chaque champ a un `label` visible et associé (`htmlFor`) — le placeholder
  n'est pas un label.
- Erreurs : annoncées (`aria-describedby` + `aria-invalid`), au niveau du
  champ, avec la correction attendue.
- `autocomplete` sur les champs standards (email, name, etc.).
- La soumission n'efface jamais ce que l'utilisateur a saisi.

## Cibles & interactions (nouveautés 2.2)

- Cibles tactiles ≥ 24px CSS minimum (44px recommandé pour le fréquent).
- Toute interaction par glissement a une alternative par clic.
- Pas d'info ou de contrôle visible uniquement au hover.

## Contenu non textuel & mouvement

- `alt` descriptif sur les images porteuses de sens, `alt=""` sur le décoratif.
- Icône seule = `aria-label` sur le bouton.
- Animations non essentielles désactivées sous `prefers-reduced-motion`.
- Rien ne clignote, l'autoplay est pausable.

## Dynamique

- Changements asynchrones annoncés : zones `aria-live="polite"` pour les
  toasts/confirmations, `role="alert"` pour les erreurs.
- Le titre de page (`<title>`) change avec la route.
- Skeleton/loading : `aria-busy` sur la zone concernée.

## Vérification

Le hook Stop lance axe-core quand un serveur tourne. Mais axe ne couvre que
~40% des critères : le parcours clavier complet du flow principal reste un
test manuel à faire à chaque feature — le rapport final doit dire s'il a été fait.
