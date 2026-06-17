# prono — règles de travail

Moteur de prédiction Coupe du Monde 2026. UI web générée en Python pur
(`ui.py`, stdlib), servie en local ou via Flask/Vercel (`api/index.py`).
Construit avec le plugin `product-builder` (voir `.claude/settings.json`).

## Domaine

Domaine actif : paris-sportifs
Utilisateurs : Baptiste, seul utilisateur — pronostics WC 2026 et décisions
de pari, consultation rapide avant les matchs, desktop et mobile.
Priorités d'usage : lisibilité avant tout ; voir d'un coup d'œil un prono
qui a changé après update des data ; ordre chronologique clair pour
reporter les pronos dans MPP ; paris lisibles tels quels pour les saisir
dans Winamax. **Desktop uniquement** (refonte dashboard 2026-06-12) ; le
mobile n'est plus une cible (décision Baptiste — on n'améliore plus le
responsive, on ne le démantèle pas pour autant).
Forme de l'UI (décidée 2026-06-12) : **dashboard à menu latéral** — sidebar
persistante (entrées : Matchs · Paris · Diagnostics), passés et futurs
fusionnés sur la page Matchs avec les passés **masquables** (repliés par
défaut), et un **filtre pays** instantané sur la liste. Parti-pris visuel
« dashboard pro » (sidebar sombre / contenu clair) — voir `design/da.md`.
Spécificités : sortie = distribution de probabilités calibrée, jamais un
score sec présenté comme certitude ; transparence du modèle (Elo, forme,
prior expert) ; aucune incitation à parier.
Résultats réels : les scores exacts (`actual_home`/`actual_away` dans
`data/fixtures.json`) arrivent par la **couche ask-Claude** — Claude récupère
les résultats post-match (accès web), Baptiste valide, Claude écrit le JSON.
Pas de saisie de score dans l'UI ; l'outil ne touche pas au réseau lui-même.
Le bilan de justesse des pronos (exact / bon / erreur) est un **cumul
tournoi** sur tous les matchs terminés — c'est un suivi a posteriori, jamais
une note de certitude (la distribution 1N2 reste l'objet premier).
Suivi des paris réels : Baptiste parie sur Winamax ; le règlement de ses
paris (gagné / perdu / remboursé) arrive par la **couche ask-Claude** comme
les scores — Baptiste dicte, Claude écrit `data/bets.json`, aucune saisie
dans l'UI. La page Paris affiche un **suivi des paris terminés** + un bilan
cumulé tournoi : **P&L (gain net) et ROI uniquement** — pas de bankroll
évolutive à tenir à jour (décision Baptiste 2026-06-12). Un pari = une ligne,
qu'il soit **simple ou combiné** (le combiné est une ligne unique : libellé
+ cote combinée + statut, sans détail par sélection). Ce bilan « argent réel »
est distinct du récap justesse des pronos (1N2). Le résultat est **lisible d'un
coup d'œil** : **gain en vert, perte en rouge** sur le P&L, et les **3 plus
gros gains** du tournoi reçoivent un **médaillon or (1er) / argent (2e) /
cuivre (3e)** — un podium perso des meilleurs paris. Outil perso
mono-utilisateur : la lisibilité du résultat prime, l'argument « incitation »
ne s'applique pas (décision Baptiste 2026-06-15).
La page Paris affiche **aussi** un bloc **Recommandations de paris** : une
sélection *value* calculée depuis le modèle et les cotes (probas ramenées vers
le marché, mises en quart-Kelly plafonnées, combinés ≤ 2 sélections), présentée
en **tableau aligné** — même grammaire que le suivi (Sélection · Cote · Mise ·
Retour), recopiable dans Winamax ; les paris **déjà posés** y sont **atténués
et regroupés** pour ne mettre en avant que le reste à jouer. Le champ
« bankroll » est un **paramètre de calibrage des mises** (quart-Kelly), pas une
bankroll évolutive à tenir à jour — la décision « pas de bankroll » porte sur
le *suivi*, pas sur ce calibrage. Cette feature est **conservée** : on recadre
sa présentation (sortie de l'esthétique en bloc/cards vers le tableau), on ne
la supprime pas (décision Baptiste 2026-06-17).

## Kit

Kit : repo `BaptisteCavalie/product-builder` (public, marketplace
`product-builder-kit`). En session cloud, les amendements /retro s'écrivent
dans un clone GitHub du kit — jamais dans le cache du plugin — et le push
revient à Baptiste tant que la session n'a pas l'accès en écriture à ce repo.

- **Mobbin (MCP)** n'est pas monté par défaut en session cloud (serveurs montés
  cette session : Excalidraw, Papers, github). Pour l'activer : déclarer le
  serveur MCP Mobbin (compte + credentials) dans la config de l'environnement.
  Sans lui, `/da` et `pattern-researcher` se rabattent sur la bibliothèque
  d'exemplaires du kit → galeries web (avec captures Playwright). <!-- 2026-06-12 -->

## Déploiement

Push sur `main` = déploiement Vercel automatique (intégration Git, entrypoint
`api/index.py`). URL de prod : à compléter par Baptiste.

## Règles de session (ajoutées par /retro)

- **Effets de bord `data/`** : lancer `ui.py` (ou toute requête sur l'UI)
  déclenche l'auto-refresh qui peut muter `data/ratings.json` et
  `data/team_status.json`. Avant tout commit, vérifier `git status` et
  restaurer ces fichiers (`git restore data/`) s'ils n'ont pas été modifiés
  volontairement. <!-- 2026-06-11 -->
- **Points d'étape** : avant un build long (> ~15 min de travail), annoncer
  le plan en une liste courte, puis poster un jalon à chaque groupe de
  corrections terminé — jamais de longue phase silencieuse. <!-- 2026-06-11 -->
- **Hygiène des branches** : chaque session cloud crée une branche `claude/*`
  et Vercel en fait un preview deploy — d'où l'accumulation de « Active
  Branches ». Une fois une branche mergée dans `main`, la supprimer
  (`git push origin --delete <branche>` ou via l'UI GitHub) pour purger les
  previews. À faire **côté GitHub/Vercel** : depuis la session cloud, la
  suppression de branche est impossible (proxy git → 403 sur la suppression de
  refs ; le MCP GitHub n'a pas de delete-branch). Avant de purger, vérifier
  qu'une branche n'a pas de commits hors `main`
  (`git log origin/main..origin/<branche>`). <!-- 2026-06-12 -->
