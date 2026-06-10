---
name: domain-knowledge
description: Connaissance métier par domaine produit (fintech, santé, e-commerce, SaaS B2B, etc.). Déclencher au début de TOUT build ou critique pour charger la référence du domaine déclaré dans le CLAUDE.md du projet — un formulaire dans une app bancaire ou médicale n'est pas un formulaire générique. Déclencher aussi quand le brief mentionne un secteur, une réglementation, ou un type d'utilisateur métier.
---

# Domain Knowledge — routeur

Ce skill ne contient pas de connaissance lui-même : il route vers la bonne
référence métier. Les références vivent dans `references/` et s'enrichissent
projet après projet via /retro et le pattern-researcher.

## Procédure

1. Lis la section `## Domaine` du CLAUDE.md du projet.
   - Elle déclare le domaine actif (ex. `fintech`) et d'éventuelles
     spécificités (ex. "B2C, clientèle senior, réglementation AMF").
2. Charge `references/<domaine>.md` et applique ses règles pendant tout le
   build et la critique, au même titre que design-judgment.
3. Si la section `## Domaine` est absente : demande à Baptiste le domaine
   AVANT de construire, puis propose de l'ajouter au CLAUDE.md du projet.

## Domaine sans référence existante

Si `references/<domaine>.md` n'existe pas :
1. Le signaler explicitement ("nouveau domaine, je bootstrap la référence").
2. Lancer le `pattern-researcher` avec pour mission : les 5-7 spécificités
   structurantes du domaine (réglementation et contraintes légales, attentes
   de confiance des utilisateurs, conventions sectorielles incontournables,
   données sensibles et leur affichage, erreurs/cas limites critiques du métier).
3. Créer `references/<domaine>.md` sur le modèle de `references/_template.md`.
4. Le faire valider par Baptiste avant le build — une référence métier fausse
   est pire que pas de référence.

## Références disponibles

- `references/fintech.md` — banque, paiement, épargne, investissement,
  assurance, crypto, KYC, produits régulés financiers.
- `references/paris-sportifs.md` — prédiction football & paris sportifs :
  probabilité implicite/vig, calibration, value betting, Kelly, ANJ.
<!-- Les nouveaux domaines s'ajoutent ici à mesure qu'ils sont bootstrappés -->

## Règle d'enrichissement

Tout apprentissage métier validé en /retro va dans la référence du domaine
actif (section "Règles ajoutées par /retro" en bas de chaque référence),
jamais dans les skills universels — design-judgment, anti-slop et a11y
restent agnostiques au domaine.
