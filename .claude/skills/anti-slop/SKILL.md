---
name: anti-slop
description: Liste des interdits visuels à vérifier sur TOUT output UI avant de le considérer terminé — composants, pages, emails, slides, SVG. Déclencher systématiquement en phase de build ET de critique, sur toute génération visuelle sans exception.
---

# Anti-slop

Le slop naît de l'absence de contraintes. Ce fichier EST la contrainte.
Chaque interdit est vérifiable en oui/non. Ce fichier s'enrichit via /retro :
chaque correction de goût de Baptiste devient une règle ici.

## Interdits absolus

**Couleur**
- ❌ Toute valeur hors tokens (`#FACC15`, `bg-yellow-400` hors système…).
- ❌ Gradients décoratifs (sur CTA, titres, fonds de cards, bordures).
- ❌ Le combo violet/indigo + fond sombre + glow "AI product".
- ❌ Bordures colorées d'accent à gauche des cards/callouts.
- ❌ Une couleur différente par item de liste/catégorie "pour faire vivant".
- ❌ Accent utilisé en décoration (fonds, icônes passives) plutôt qu'en signal.

**Typographie**
- ❌ Plus de 2 graisses par écran.
- ❌ Alternance de graisses dans une même phrase pour "dynamiser".
- ❌ Mots isolés en couleur d'accent au milieu d'un titre.
- ❌ Tout en capitales sur plus de 3 mots (hors micro-labels avec letter-spacing).
- ❌ Tailles de police hors échelle des tokens.

**Composition**
- ❌ Ombres portées sur les cards de contenu statique — l'élévation est réservée
  aux éléments flottants (modale, dropdown, toast).
- ❌ Border + ombre + fond teinté cumulés sur un même conteneur (choisir UN
  séparateur, ou juste l'espace).
- ❌ Coins arrondis incohérents (un seul radius de tokens par famille de composants).
- ❌ Cards imbriquées dans des cards.
- ❌ La grille de 3 cards "features" avec icône centrée + titre + paragraphe,
  par réflexe — ce pattern doit être justifié, pas défaut.

**Iconographie & ornement**
- ❌ Emojis comme icônes ou puces dans l'UI produit.
- ❌ Icône devant CHAQUE titre, item de menu ou cellule — l'icône doit ajouter
  du sens, sinon rien.
- ❌ Illustrations 3D génériques type "blob people" / memphis / isométrique stock.
- ❌ Sparkles ✨ et toute imagerie "magie IA".

**Copy**
- ❌ "Supercharge", "Unleash", "Seamless", "Effortless", "Élevez votre…",
  "Boostez", "révolutionnaire" et tout superlatif vide.
- ❌ Point d'exclamation dans l'UI (réservé aux vraies célébrations, max 1).
- ❌ Tirets cadratins en cascade et tournures "It's not just X, it's Y".

**Layout**
- ❌ Hero centré + badge pilule "New ✨" + titre 3 lignes + 2 CTA côte à côte,
  par défaut — encore une fois : possible si justifié, interdit par réflexe.
- ❌ Sections alternées image-gauche/image-droite sur toute une landing.

## Le test final

Avant de rendre un écran, pose la question : "Est-ce qu'on peut deviner que
c'est généré par IA en 2 secondes ?" Si oui, identifie l'indice et supprime-le.
Le but n'est pas la sobriété pour la sobriété — c'est que chaque choix visuel
soit une décision, pas un réflexe statistique.

## Règles ajoutées par /retro

<!-- Les amendements validés par Baptiste s'ajoutent ici, datés -->
