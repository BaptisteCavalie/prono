---
description: Audit de l'existant par les critics, sans construction. Utile sur un projet ou un écran déjà fait.
argument-hint: [quoi auditer : URL, page, composant, ou "tout"]
---

# /critique — Audit sans build

Cible : $ARGUMENTS

1. Si une URL ou un dev server est disponible, capture desktop + mobile :
   ```bash
   npx playwright screenshot --viewport-size=1440,900 <url> /tmp/review-desktop.png
   npx playwright screenshot --viewport-size=390,844 <url> /tmp/review-mobile.png
   ```
2. Lance en parallèle `design-critic` (screenshots + code de la cible) et
   `code-reviewer` (fichiers de la cible). Présente le travail comme celui
   d'une équipe externe.
3. NE CORRIGE RIEN. Rends uniquement le rapport consolidé :
   - issues par sévérité, chacune avec : où, quoi, quel principe est violé,
     correction proposée, effort estimé (S/M/L) ;
   - un ordre de traitement recommandé (blockers d'abord, puis le meilleur
     ratio impact/effort).
4. Demande à Baptiste ce qu'il veut corriger avant de toucher au code.
