---
description: Rétrospective de session — transforme les corrections de Baptiste en règles permanentes dans les skills
---

# /retro — La boucle d'apprentissage

C'est par cette commande que le système s'améliore. Exécute en fin de session.

## 1. Relis la session

Parcours la conversation et identifie :
- chaque correction manuelle de Baptiste (code, design, copy, scope) ;
- chaque reproche ou désaccord exprimé, même en passant ("non pas comme ça",
  "je préfère", "c'est moche", "trop chargé") ;
- chaque question qu'il a dû poser parce qu'une info manquait au rapport ;
- les issues critics qu'il a ignorées ou contredites (signal que la rubrique
  est mal calibrée).

## 2. Transforme en amendements

Pour chaque signal, propose un amendement à UN fichier précis :
- goût visuel récurrent → `skills/anti-slop` ou `skills/design-judgment`
- accessibilité → `skills/a11y`
- domaine métier → `skills/domain-knowledge/references/<domaine actif>.md`
- critère de jugement mal calibré → l'agent critic concerné
- processus / arbitrage → `CLAUDE.md` ou la commande concernée

Règles de rédaction d'un amendement :
- **Généralise** : pas "Baptiste n'a pas aimé l'ombre sur la card pricing" mais
  "Pas d'ombre portée sur les cards de contenu statique ; réserver l'élévation
  aux éléments flottants (modales, dropdowns, toasts)".
- Une règle = une ligne testable. Si on ne peut pas vérifier qu'elle est
  respectée, reformule.
- Vérifie qu'elle ne contredit pas une règle existante. Si conflit, propose
  la résolution explicitement.

## 3. Validation

Présente les amendements en liste numérotée : fichier cible, règle proposée,
signal d'origine (citation courte). Attends la validation de Baptiste
**amendement par amendement**. N'écris RIEN dans les skills sans validation.

## 4. Applique et logge

- Écris les amendements validés dans les fichiers cibles.
- Ajoute la ligne de télémétrie de la session dans `telemetry/runs.jsonl`
  si ce n'est pas déjà fait.
- Termine par : nombre de règles ajoutées, et s'il y a un pattern dans la
  télémétrie récente (même dimension faible sur ≥3 runs → signale que le
  skill correspondant a probablement un trou structurel).
