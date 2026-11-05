#!/bin/zsh
# Actualiza claude.svg con el uso local de Claude Code y lo sube a GitHub.
# Lo corre a diario la tarea de launchd io.vmmendozae.claude-stats.
set -euo pipefail

# Refleja la actividad de GitLab en el repo privado gitlab-contributions.
GL="$HOME/.local/share/gitlab-contributions"
if [ -d "$GL" ]; then
  (cd "$GL" && /usr/bin/python3 -I sync.py && git push -q) || echo "La sincronización con GitLab falló; sigo con Claude."
fi
cd "$(dirname "$0")/.."
git pull -q --rebase
/usr/bin/python3 -I scripts/claude_stats.py "$PWD"
git add claude.svg data/claude-usage.json
git diff --cached --quiet || git commit -qm "Actualizar uso de Claude Code"
# GitHub a veces rechaza el push con un error pasajero: reintenta una vez.
git push -q || { sleep 30; git pull -q --rebase; git push -q; }
