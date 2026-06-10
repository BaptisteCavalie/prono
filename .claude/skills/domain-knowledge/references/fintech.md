# Fintech & produits régulés

Expérience condensée : banque de détail (millions de MAU), paiements
européens (Wero/EPI), assurance-vie, gestion d'actifs. Dans un produit
financier, la confiance EST le produit — chaque détail visuel la construit
ou la détruit.

## Confiance

- La confiance vient de la précision, pas de la décoration : alignements
  parfaits, chiffres exacts, zéro incohérence. Une virgule mal placée dans
  un montant détruit plus de confiance qu'un design daté.
- Sobriété chromatique : la couleur signale (positif/négatif/attention),
  elle ne décore pas. Pas de gamification visuelle sur l'argent des gens.
- Jamais de dark pattern : pas d'option pré-cochée engageante, pas de
  frais découverts en fin de tunnel, résiliation aussi simple que souscription.
  Au-delà de l'éthique : en produit régulé, c'est un risque légal.

## Montants & données financières

- `tabular-nums` partout où des chiffres s'empilent ou se comparent.
- Format local strict (fr : `1 234,56 €` — espace insécable, virgule).
- Négatif = signe ET couleur ET jamais couleur seule. Positif explicite (+)
  dans les listes de mouvements.
- Arrondis : afficher arrondi, calculer exact, et permettre de voir l'exact.
- Un montant total a toujours sa décomposition accessible (frais inclus visibles).

## Opérations sensibles (virement, paiement, souscription)

- Pattern en 3 temps : saisie → **récapitulatif explicite** (montant,
  bénéficiaire, date d'exécution, frais) → confirmation forte (SCA si requis).
- L'état "en cours" est un vrai état : une opération financière n'est ni
  instantanée ni binaire — afficher initiée / en traitement / exécutée / rejetée.
- Confirmation = preuve : référence, horodatage, récapitulatif réutilisable.
- L'irréversible est annoncé AVANT, pas après.

## KYC & onboarding régulé

- Annoncer la couleur dès l'entrée : étapes, pièces nécessaires, durée estimée.
  L'abandon vient de l'incertitude plus que de la longueur.
- Une information par écran dans les passages sensibles ; sauvegarder à
  chaque étape (on reprend où on s'était arrêté).
- Expliquer POURQUOI chaque donnée est demandée (obligation légale ≠ curiosité
  produit — le dire augmente la complétion).
- Les temps morts (vérification d'identité) : dire ce qui se passe et quand
  l'utilisateur aura la réponse, par quel canal.

## Erreurs & cas limites — là où la fintech se joue

- Un rejet (paiement, virement, document) n'est jamais une impasse : cause
  en langage humain + action suivante + recours.
- Jamais de jargon réglementaire exposé brut (pas de "SCA requise" → "Confirmez
  avec votre application bancaire").
- Solde insuffisant, plafond atteint, compte bloqué : prévoir ces écrans
  AVANT l'écran de succès. C'est eux que les utilisateurs stressés verront.

## Conformité & design

- Mentions légales : présentes mais hiérarchisées — le légal n'a pas à crier,
  il doit être trouvable et lisible (pas de gris 3:1 en corps 10px).
- Performances passées ≠ futures, risques produits (investissement) : intégrés
  au flow, pas cachés dans un PDF.
- RGPD : consentements granulaires, refus aussi simple que l'accord.
- eIDAS 2.0 / EUDI Wallet : pour l'identité, anticiper les parcours de
  vérification par wallet — pattern émergent à surveiller dans les briefs.

## Règles ajoutées par /retro

<!-- Amendements validés, datés -->
