---
description: Pipeline complet de construction d'une feature, du challenge produit au rapport final
argument-hint: [description de la feature]
---

# /feature — Pipeline de construction

Feature demandée : $ARGUMENTS

Exécute ce pipeline dans l'ordre, sans sauter d'étape. Chaque étape produit un
livrable qui nourrit la suivante.

## Étape 1 — Challenge produit

Lance le subagent `product-challenger` avec le brief.
- S'il rend un verdict `rethink`, STOP : présente son analyse à Baptiste et
  attends sa décision. Ne construis rien.
- Sinon, récupère le **scope retenu** (la version minimale à forte valeur) et
  les critères de succès. C'est CE scope que tu construis, pas le brief initial.

## Étape 2 — Recherche de patterns

1. Consulte d'abord `patterns/` : si un brief existant couvre ≥70% du sujet,
   utilise-le et passe à l'étape 3.
2. Sinon, lance le subagent `pattern-researcher` avec le scope retenu.
   Il rend un pattern brief d'une page max.
3. Sauvegarde ce brief dans `patterns/<sujet>.md` (format de `patterns/_template.md`).

## Étape 3 — Build

Construis le scope retenu en appliquant les skills `design-judgment`,
`anti-slop`, `a11y` et `domain-knowledge` (qui charge la référence du
domaine déclaré dans le CLAUDE.md du projet).
- Tokens de `design-system/tokens.css` uniquement.
- Tous les états des composants interactifs dès le premier jet.
- Commits atomiques avec messages clairs.

## Étape 4 — Vérification visuelle

Si un dev server peut tourner et que Playwright est disponible :
```bash
npx playwright screenshot --viewport-size=1440,900 <url> /tmp/review-desktop.png
npx playwright screenshot --viewport-size=390,844 <url> /tmp/review-mobile.png
```
Sinon, note que la revue se fera sur code et signale-le dans le rapport.

## Étape 5 — Critique (parallèle)

Lance EN PARALLÈLE :
- `design-critic` — avec les screenshots (ou le code), le scope retenu et le
  pattern brief. IMPORTANT : présente-lui le travail comme celui d'une équipe
  externe à auditer, jamais comme le tien.
- `code-reviewer` — avec les fichiers modifiés.

## Étape 6 — Boucle de correction

- S'il reste des issues `blocker` ou `major` : corrige-les TOUTES, puis relance
  les critics concernés. Maximum **3 tours**.
- Corrige les `minor` au passage, logge les `nit` sans les corriger.
- Si 3 tours atteints OU deux tours sans progrès matériel OU oscillation :
  STOP + rapport d'escalade.

## Étape 7 — Rapport final

Termine par un rapport court :
- **Shippé** : ce qui a été construit, écart éventuel avec le brief initial et pourquoi.
- **Verdicts** : synthèse des critics (nombre d'issues par sévérité, tours de boucle).
- **Tranché** : les arbitrages faits en autonomie.
- **À décider** : ce qui mérite l'œil de Baptiste (ambiguïtés, dette notée, nits récurrents).
- **Preview** : URL Vercel si déployé.

Puis ajoute une ligne dans `telemetry/runs.jsonl` :
```json
{"date":"<ISO>","feature":"<nom>","tours":N,"blockers":N,"majors":N,"minors":N,"nits":N,"escalade":false,"dimensions_faibles":["..."]}
```
