#!/usr/bin/env bash
# Captures de revue de l'UI (desktop + mobile) — rejouables à chaque tour de
# boucle de correction. Démarre un serveur ui.py éphémère, shoote les onglets
# demandés, puis restaure les effets de bord data/ (ratings/team_status).
#
# Usage : tools/screenshots.sh [tab ...]    (défaut : futurs passes paris)
# Sorties : /tmp/review-<tab>-desktop.png et /tmp/review-<tab>-mobile.png
set -euo pipefail
cd "$(dirname "$0")/.."

TABS=("$@")
[ ${#TABS[@]} -eq 0 ] && TABS=(futurs passes paris)

PORT=8011
python3 ui.py --port "$PORT" >/tmp/ui-shot.log 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null || true; git restore data/ratings.json data/team_status.json 2>/dev/null || true' EXIT

for _ in $(seq 1 20); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break || sleep 0.5
done

for tab in "${TABS[@]}"; do
  npx playwright screenshot --full-page --viewport-size=1440,900 \
    "http://127.0.0.1:$PORT/?tab=$tab" "/tmp/review-$tab-desktop.png"
  npx playwright screenshot --full-page --viewport-size=390,844 \
    "http://127.0.0.1:$PORT/?tab=$tab" "/tmp/review-$tab-mobile.png"
  echo "captured $tab"
done
