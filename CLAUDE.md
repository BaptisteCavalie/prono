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
dans Winamax. Desktop d'abord (refonte 2026-06-11), le mobile suit.
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

## Kit

Kit : repo `BaptisteCavalie/product-builder` (public, marketplace
`product-builder-kit`). En session cloud, les amendements /retro s'écrivent
dans un clone GitHub du kit — jamais dans le cache du plugin — et le push
revient à Baptiste tant que la session n'a pas l'accès en écriture à ce repo.

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
