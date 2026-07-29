#!/bin/bash
#
# Rend le plugin product-builder disponible en session Claude Code sur le web.
#
# Pourquoi ce hook existe : déclarer un plugin dans .claude/settings.json ne
# l'installe pas. Pour une source externe (dépôt GitHub), Claude Code attend
# qu'un humain accepte une invite d'installation. En session cloud, personne ne
# clique — le plugin reste absent, et /da, /feature, /critique, /retro avec lui.
# Ce hook fait l'installation à notre place.
#
# Volontairement tolérant : si l'installation échoue (réseau, dépôt
# indisponible), la session démarre quand même, sans le plugin.

set -uo pipefail

MARKETPLACE_DEPOT="BaptisteCavalie/product-builder"
MARKETPLACE="product-builder-kit"
PLUGIN="product-builder@${MARKETPLACE}"

# En local, l'installation se fait une fois pour toutes et persiste dans
# ~/.claude/plugins — inutile de la rejouer à chaque session.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

if ! command -v claude > /dev/null 2>&1; then
  echo "product-builder : CLI claude introuvable, installation ignorée." >&2
  exit 0
fi

# Idempotence : ne rien refaire si le plugin est déjà là.
if claude plugin list 2>/dev/null | grep -q "$PLUGIN"; then
  exit 0
fi

if ! claude plugin marketplace add "$MARKETPLACE_DEPOT" > /dev/null 2>&1; then
  # La marketplace peut déjà être connue : on tente l'installation malgré tout.
  echo "product-builder : ajout de la marketplace sans effet, poursuite." >&2
fi

if claude plugin install "$PLUGIN" > /dev/null 2>&1; then
  echo "product-builder installé — /da, /feature, /critique et /retro disponibles."
else
  echo "product-builder : installation impossible, session démarrée sans le plugin." >&2
fi

exit 0
