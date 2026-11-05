#!/bin/zsh
# Actualiza claude.svg con el uso local de Claude Code y lo sube a GitHub.
# Lo corre a diario la tarea de launchd io.vmmendozae.claude-stats.
set -euo pipefail
cd "$(dirname "$0")/.."
git pull -q --rebase
/usr/bin/python3 -I scripts/claude_stats.py "$PWD"
git add claude.svg data/claude-usage.json
git diff --cached --quiet || { git commit -qm "Actualizar uso de Claude Code" && git push -q; }
