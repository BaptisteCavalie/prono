# prono — règles de travail

Moteur de prédiction Coupe du Monde 2026. UI web générée en Python pur
(`ui.py`, stdlib), servie en local ou via Flask/Vercel (`api/index.py`).

## Règles de session (ajoutées par /retro)

- **Effets de bord `data/`** : lancer `ui.py` (ou toute requête sur l'UI)
  déclenche l'auto-refresh qui peut muter `data/ratings.json` et
  `data/team_status.json`. Avant tout commit, vérifier `git status` et
  restaurer ces fichiers (`git restore data/`) s'ils n'ont pas été modifiés
  volontairement. <!-- 2026-06-11 -->
- **Points d'étape** : avant un build long (> ~15 min de travail), annoncer
  le plan en une liste courte, puis poster un jalon à chaque groupe de
  corrections terminé — jamais de longue phase silencieuse. <!-- 2026-06-11 -->
