# 3D Library Manager

Bibliothèque personnelle de fichiers d'impression 3D : dépose un fichier
(`.zip` Thingiverse/Printables, `.stl`, `.3mf`) dans `~/3D`, il est
automatiquement extrait, analysé (dimensions, volume, poids, temps
d'impression estimé), tagué, miniaturé et rangé dans `~/3D_Library/`.
Une interface web permet de parcourir/rechercher la bibliothèque et
d'envoyer un modèle vers OrcaSlicer.

Voir `docs/SPECS.md` pour la spec d'origine du projet, et
`docs/superpowers/` pour l'historique des décisions de conception
(spécifications et plans d'implémentation datés).

## Architecture en un coup d'œil

```
~/3D                         (dépôt unique, surveillé)
  │  systemd --user path/timer unit (zéro process au repos)
  ▼
scanner.py  →  ~/3D_Library/ (models/, _originals/, library.db)
                                │
                                ▼
                   webapp.py (FastAPI, activation par socket)
                                │
                                ▼
                     http://localhost:8000
```

Aucun process ne tourne en permanence : le watcher (`scanner.py`) est
déclenché par un `systemd --user path unit` (inotify, avec un `.timer` de
secours toutes les 5 min), et l'interface web n'est démarrée qu'à la
première connexion (`systemd --user socket unit`), puis s'arrête seule
après 10 minutes d'inactivité.

## 1. Dépendances

### Système (Ubuntu/Debian)

```bash
sudo apt install f3d xvfb   # génération des miniatures (F3D, rendu headless)
```

OrcaSlicer doit être installé séparément si tu veux utiliser le bouton
« Ouvrir dans OrcaSlicer » (Flatpak, AppImage, ou paquet — voir la variable
`ORCASLICER_CMD` plus bas).

### Python

Ce projet n'utilise pas de venv (installation globale avec
`--break-system-packages` sur Debian/Ubuntu récent, PEP 668) :

```bash
pip install --user --break-system-packages -r requirements.txt
```

`networkx` et `lxml` sont requis par trimesh pour charger les `.3mf` (pas
seulement les `.stl`) — sans eux, les `.3mf` sont catalogués avec des
champs d'analyse vides (dimensions/volume/poids à `null`), sans erreur
visible.

## 2. Premier scan (import du stock existant)

Avant d'activer le watcher automatique, importe une première fois ce qui
traîne déjà dans `~/3D` :

```bash
mkdir -p ~/3D ~/3D_Library
python3 scanner.py --source ~/3D --library ~/3D_Library
```

`~/3D` doit être réservé aux fichiers à cataloguer — pas de projets CAD en
cours (FreeCAD, etc.), qui ont vocation à vivre ailleurs (`~/Documents/FreeCAD`
par exemple) et à n'être copiés dans `~/3D` qu'une fois leur export final
prêt à imprimer.

## 3. Installation des services systemd (watcher + interface web)

Tout se fait en utilisateur (`systemd --user`), sans sudo. Les fichiers
unités vivent dans `systemd/` et sont symlinkés dans
`~/.config/systemd/user/` pour rester versionnés et à jour avec le repo.

```bash
mkdir -p ~/.config/systemd/user

# Watcher : scan automatique de ~/3D
ln -sf ~/Documents/Code/3d/library/systemd/3d-library-watch.path   ~/.config/systemd/user/
ln -sf ~/Documents/Code/3d/library/systemd/3d-library-watch.service ~/.config/systemd/user/
ln -sf ~/Documents/Code/3d/library/systemd/3d-library-watch.timer  ~/.config/systemd/user/

# Interface web : démarrage à la demande, arrêt après inactivité
ln -sf ~/Documents/Code/3d/library/systemd/3d-library-web.socket   ~/.config/systemd/user/
ln -sf ~/Documents/Code/3d/library/systemd/3d-library-web.service  ~/.config/systemd/user/

systemctl --user daemon-reload

systemctl --user enable --now 3d-library-watch.path
systemctl --user enable --now 3d-library-watch.timer
systemctl --user enable --now 3d-library-web.socket

# Pour que les services tournent même sans session graphique ouverte
# (et survivent à une déconnexion) :
loginctl enable-linger "$USER"
```

Adapte les chemins ci-dessus si le repo n'est pas dans
`~/Documents/Code/3d/library` (les fichiers `.service` utilisent `%h` pour
le `$HOME`, mais les symlinks doivent pointer vers le bon chemin absolu).

### Vérifier que tout tourne

```bash
systemctl --user status 3d-library-watch.path    # doit afficher "active (waiting)"
systemctl --user status 3d-library-watch.timer    # doit afficher "active (running)"
systemctl --user status 3d-library-web.socket     # doit afficher "active (listening)"

# Aucun process résident entre deux déclenchements/connexions :
pgrep -af "watch_trigger.py|webapp.py"            # ne doit rien afficher au repos
```

### Logs

```bash
journalctl --user -u 3d-library-watch.service -f   # suit un scan en direct
journalctl --user -u 3d-library-web.service -f      # suit l'interface web
```

## 4. Utilisation

- **Cataloguer un modèle** : dépose un `.zip`/`.stl`/`.3mf` dans `~/3D`.
  Rien d'autre à faire — le watcher s'en occupe (jusqu'à ~12s de délai pour
  laisser le temps à une copie/téléchargement de se terminer).
- **Parcourir la bibliothèque** : ouvre `http://localhost:8000`. Démarre
  tout seul à la première visite (quelques centaines de ms), s'arrête tout
  seul après 10 min d'inactivité.
- **Lancer manuellement** (sans passer par systemd, ex. pour du
  développement) :
  ```bash
  LIBRARY_DB_PATH=~/3D_Library/library.db python3 webapp.py --library ~/3D_Library --port 8000
  ```

## 5. Interface web (frontend React)

L'interface servie par `webapp.py` est une app React/TypeScript buildée avec
Vite (`frontend/`), chargée depuis `frontend/dist/` — pas de serveur Node en
production.

**Développement** (hot reload, proxy vers le backend FastAPI) :

```bash
cd frontend
npm install
npm run dev        # serveur de dev Vite sur http://localhost:5173, proxy /api vers http://127.0.0.1:8000
```

Lance le backend en parallèle (`LIBRARY_DB_PATH=~/3D_Library/library.db python3 webapp.py --port 8000`)
pour que le proxy ait quelque chose à relayer.

**Production** (ce que sert réellement `webapp.py`) :

```bash
cd frontend
npm run build       # génère frontend/dist, servi par FastAPI à la racine
```

`frontend/node_modules` et `frontend/dist` sont ignorés par git — à builder
une fois après chaque clone/déploiement.

## 6. Variables d'environnement

| Variable | Défaut | Usage |
|---|---|---|
| `LIBRARY_DB_PATH` | `library.db` (dossier courant) | Chemin vers `library.db`, lu par `webapp.py` |
| `IDLE_TIMEOUT_SECONDS` | `600` (10 min) | Délai d'inactivité avant l'arrêt auto de `webapp.py` (actif uniquement sous activation par socket) |
| `ORCASLICER_CMD` | `flatpak run com.orcaslicer.OrcaSlicer` | Commande pour ouvrir un modèle dans OrcaSlicer (Linux) |
| `TRASH_RETENTION_DAYS` | `30` | Nombre de jours avant purge définitive d'un modèle mis à la corbeille (lu par `webapp.py` et `purge_trash.py`) |

## 7. Tests

```bash
python3 -m pytest -v
```

76 tests, aucune dépendance système requise au-delà de `requirements.txt`
(les tests mockent `analyze_stl`/`f3d` sauf un test d'intégration réel sur
un `.3mf` minimal généré à la volée).

## 8. Désinstaller / désactiver

```bash
systemctl --user disable --now 3d-library-watch.path 3d-library-watch.timer 3d-library-web.socket
rm ~/.config/systemd/user/3d-library-watch.{path,service,timer} ~/.config/systemd/user/3d-library-web.{socket,service}
systemctl --user daemon-reload
```

Les données (`~/3D_Library/`) et les originaux archivés
(`~/3D_Library/_originals/`) ne sont jamais supprimés par cette opération.
