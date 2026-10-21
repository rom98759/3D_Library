# 3D Library Manager

## But
Bibliothèque personnelle de fichiers d'impression 3D : watcher qui catalogue
automatiquement les dépôts (`.zip` Thingiverse/Printables, `.stl`, `.3mf`) dans
`~/3D`, les analyse (dimensions, volume, poids, temps d'impression), les range
dans `~/3D_Library/`, avec UI web pour parcourir/rechercher et envoyer vers
OrcaSlicer. Statut : actif, usage perso.

## Stack & architecture
- Backend Python : `scanner.py` (watcher/catalogage), `stl_analysis.py`
  (trimesh), `thumbnails.py` (rendu f3d headless), `auto_tag.py`,
  `purge_trash.py` (corbeille), `watch_trigger.py`, `webapp.py` (FastAPI).
- Frontend `frontend/` : React 19 + TS + Vite + Tailwind, buildé en
  `frontend/dist/` et servi statiquement par `webapp.py` (pas de serveur Node
  en prod).
- Deux modes de déploiement : Docker (`docker-compose.yml`, un seul conteneur)
  ou systemd --user natif (`systemd/*.path|.service|.socket|.timer`, zéro
  process au repos, watcher inotify + web activée par socket).
- Flux : `~/3D` → `scanner.py` → `~/3D_Library/` (models/, _originals/,
  library.db) → `webapp.py` → `http://library3d.localhost:8765` (ou
  `:8000` en Docker).

## Commandes
- Installer (natif) : `pip install --user --break-system-packages -r requirements.txt`
  puis `sudo apt install f3d xvfb` (miniatures).
- Premier scan : `python3 scanner.py --source ~/3D --library ~/3D_Library`
- Lancer web (dev, natif) : `LIBRARY_DB_PATH=~/3D_Library/library.db python3 webapp.py --library ~/3D_Library --port 8765`
- Lancer via Docker : `docker compose up --build -d` puis `http://localhost:8000`
  (rescanner : `docker compose exec app python3 scanner.py --source /data/incoming --library /data/library`)
- Frontend dev : `cd frontend && npm install && npm run dev` (proxy `/api` → `:8765`)
- Build frontend (prod) : `cd frontend && npm run build`
- Lint frontend : `cd frontend && npm run lint`
- Tests : `python3 -m pytest -v`
- Arrêter (natif) : `systemctl --user disable --now 3d-library-watch.path 3d-library-watch.timer 3d-library-web.socket 3d-library-purge.timer`

## Conventions propres au projet
- Pas de venv : installation Python globale (`--break-system-packages`, PEP 668).
- `~/3D` réservé aux fichiers à cataloguer, jamais de projets CAD en cours.
- Tests mockent `analyze_stl`/`f3d` sauf un test d'intégration réel sur un
  `.3mf` minimal généré à la volée.

## Pièges connus
- Sans `networkx`/`lxml`, les `.3mf` sont catalogués mais avec dimensions/
  volume/poids à `null`, sans erreur visible.
- Sans `f3d`, le catalogage fonctionne mais sans miniature (non inclus dans
  l'image Docker pour la garder légère).
- Nom local `library3d.localhost` : nécessite une ligne `/etc/hosts` manuelle.
- `frontend/node_modules` et `frontend/dist` ignorés par git — à rebuilder
  après chaque clone/déploiement.
- Variables d'env utiles : `LIBRARY_DB_PATH`, `IDLE_TIMEOUT_SECONDS`,
  `ORCASLICER_CMD`, `TRASH_RETENTION_DAYS`, `PORT` (Docker).
