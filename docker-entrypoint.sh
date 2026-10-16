#!/usr/bin/env bash
# Prépare la bibliothèque puis lance la commande (uvicorn par défaut).
#
# webapp.py renvoie une 503 tant que library.db n'existe pas : on lance donc
# un premier scan de INCOMING_DIR (crée la base + importe ce qui s'y trouve).
# Déposer de nouveaux fichiers ensuite : les copier dans ./data/incoming puis
#   docker compose exec app python3 scanner.py --source "$INCOMING_DIR" --library "$LIBRARY_DIR"
set -euo pipefail

INCOMING_DIR="${INCOMING_DIR:-/data/incoming}"
LIBRARY_DIR="${LIBRARY_DIR:-/data/library}"

log() { echo "[entrypoint $(date -u +%H:%M:%S)] $*"; }

mkdir -p "$INCOMING_DIR" "$LIBRARY_DIR"

log "scan initial : $INCOMING_DIR -> $LIBRARY_DIR"
python3 scanner.py --source "$INCOMING_DIR" --library "$LIBRARY_DIR" \
    || log "scan terminé (ou rien à importer)"

log "démarrage : $*"
exec "$@"
