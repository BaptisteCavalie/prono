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

## Règles de session (ajoutées par /retro)

- **Effets de bord `data/`** : lancer `ui.py` (ou toute requête sur l'UI)
  déclenche l'auto-refresh qui peut muter `data/ratings.json` et
  `data/team_status.json`. Avant tout commit, vérifier `git status` et
  restaurer ces fichiers (`git restore data/`) s'ils n'ont pas été modifiés
  volontairement. <!-- 2026-06-11 -->
- **Points d'étape** : avant un build long (> ~15 min de travail), annoncer
  le plan en une liste courte, puis poster un jalon à chaque groupe de
  corrections terminé — jamais de longue phase silencieuse. <!-- 2026-06-11 -->
