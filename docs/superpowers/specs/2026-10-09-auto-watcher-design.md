# 3D Library Manager — Automatisation du dépôt (watcher) + réorganisation des dossiers

Date : 2026-10-09
Statut : approuvé par l'utilisateur, prêt pour le plan d'implémentation

## Contexte

Le projet `3D Library Manager` (`~/Documents/Code/3d/library`) existe depuis août 2026 et
fonctionne déjà manuellement : `scanner.py --source <dossier> --library ~/3D_Library` scanne
un dossier, extrait les ZIP, analyse les STL (trimesh), génère des miniatures, tague
automatiquement, et range tout dans `~/3D_Library/models/<catégorie>/<nom>/`. Une interface
web (`webapp.py` + `static/index.html`) permet de parcourir la bibliothèque, avec un bouton
pour ouvrir un modèle dans OrcaSlicer.

Problème signalé par l'utilisateur : il doit lancer le scan à la main, penser à le faire, et
les fichiers 3D sont éparpillés entre `~/3D` (en réalité des projets FreeCAD actifs, pas des
téléchargements), `~/Téléchargements` (mélange de tout), et `~/3D_Library` (la base déjà
cataloguée). Objectif : déposer un fichier à un seul endroit et que tout se passe sans aucune
action manuelle, en restant aussi léger que possible en RAM/CPU.

Audit réalisé (session du 2026-10-09) :

- `~/3D` (45 Mo) : projets FreeCAD en cours (`FFM_Trophy/`, `Laptop-stand/`, `DemoEquerre.FCStd`)
  + quelques exports isolés (`Orsetto_Portachiavi.stl`, `porte_cle_42-*.3mf`)
- `~/Téléchargements` (2,2 Go) : 9 ZIP + 6 STL isolés + plusieurs `.3mf` jamais importés dans
  la bibliothèque, mélangés à des fichiers sans rapport (PDF, CSV, gcode, etc.)
- `~/3D_Library` (1,1 Go, 194 modèles) : bibliothèque déjà peuplée, fonctionne bien
- `~/freecad-workspace/` et `~/Documents/FreeCAD/` : deux emplacements FreeCAD différents
  (incohérence historique à corriger)
- Repo git `3d/library` propre, 3 commits non pushés sur `origin/main`

Décisions prises avec l'utilisateur :

- `~/3D` devient **l'unique point de dépôt** : tout ce qui doit finir dans la bibliothèque
  (téléchargement Thingiverse, export FreeCAD terminé, etc.) y est déposé, et rien d'autre.
- Les projets FreeCAD actifs sont centralisés dans `~/Documents/FreeCAD/` (plus de
  `~/freecad-workspace/`, plus de fichiers FreeCAD dans `~/3D`).
- OctoPrint est hors scope : le bouton existant « ouvrir dans OrcaSlicer » est conservé tel
  quel, pas d'automatisation d'impression.
- La recherche sémantique IA (V3 de `docs/SPECS.md`) reste hors scope.

## Objectif

1. Réorganiser les dossiers une bonne fois pour toutes (FreeCAD d'un côté, dépôt 3D de l'autre).
2. Importer le stock existant non traité.
3. Mettre en place un déclenchement automatique du scanner dès qu'un fichier apparaît dans
   `~/3D`, sans processus résident ni polling — le plus léger possible.
4. Combler une lacune découverte pendant l'audit : `scanner.py` ne traite pas les `.3mf`
   (plusieurs fichiers de l'utilisateur sont dans ce format).

## Architecture

```
   ~/3D  (dépôt unique, surveillé)
     |
     |  inotify (noyau, zéro coût au repos)
     v
  systemd --user path unit  (3d-library-watch.path)
     |
     |  déclenche au moindre changement
     v
  systemd --user service (oneshot)  (3d-library-watch.service)
     |
     |  attend la stabilité des fichiers (pas de modif depuis 10s)
     v
  scanner.py --source ~/3D --library ~/3D_Library
     |
     +--> extraction ZIP, analyse STL/3MF (trimesh), tags auto, miniature (f3d)
     +--> rangement dans ~/3D_Library/models/<catégorie>/<nom>/
     +--> original archivé dans ~/3D_Library/_originals/ (comportement existant, inchangé)
     +--> ligne ajoutée dans library.db (SQLite)

  ~/Documents/FreeCAD/   <-- projets FreeCAD actifs, jamais touchés par le watcher
```

### Pourquoi un path unit plutôt qu'un daemon Python (`watchdog`)

Un service Python avec la lib `watchdog` reste résident en mémoire (process Python + imports
trimesh/numpy chargés en permanence, plusieurs dizaines de Mo) même quand rien ne se passe.
Un `systemd --user path unit` utilise `inotify` au niveau noyau : **aucun process ne tourne**
entre deux dépôts de fichiers. systemd ne lance le script Python (donc ne charge trimesh en
mémoire) que pendant les quelques secondes du traitement, puis le process se termine. C'est
strictement plus léger, et c'est un mécanisme natif déjà présent sur Ubuntu (pas de dépendance
supplémentaire).

### Débounce / anti doublon

Les téléchargements de zip volumineux ou les copies de fichiers ne sont pas instantanés, et un
`.zip` qui arrive génère lui-même d'autres événements inotify quand il est extrait. Pour éviter
de traiter un fichier à moitié écrit :

- Le script déclenché par le `.service` liste les fichiers de `~/3D`, et **ignore tout fichier
  dont le `mtime` date de moins de 10 secondes**. Si rien n'est "mûr", il s'arrête sans rien
  faire.
- Comme le `.path` unit redéclenche à chaque modification du dossier, le fichier finira par
  être traité au prochain événement une fois stable (téléchargement terminé).
- `scanner.py` est déjà idempotent (colonnes `UNIQUE` sur `path` et `file_hash` dans `models`,
  cf. `init_db`) : même si le service se déclenche plusieurs fois sur le même fichier avant
  qu'il soit retiré de `~/3D`, aucun doublon n'est créé en base.
- systemd garantit qu'une seule instance du `.service` (oneshot) tourne à la fois pour une
  unité donnée ; un déclenchement pendant que le précédent traite encore une archive ne lance
  pas une deuxième exécution concurrente.

## Changements de code

### 1. Support `.3mf` dans `scanner.py` / `stl_analysis.py` / `thumbnails.py`

Actuellement seuls `.zip` et `.stl` sont reconnus (`scan_source`, `find_stl_files`). Trimesh
sait déjà charger un `.3mf` (`trimesh.load(..., force="mesh")` fonctionne tel quel dans
`stl_analysis.analyze_stl`, aucun changement nécessaire côté analyse). Changements requis :

- `find_stl_files` (scanner.py) : reconnaître aussi `*.3mf`, pas seulement `*.stl`.
- La boucle "STL isolés" dans `scan_source` : filtrer sur `{".stl", ".3mf"}` au lieu de
  `.stl` seul.
- `insert_model` : le fichier final rangé dans la bibliothèque est nommé `model<extension
  d'origine>` (`model.stl` ou `model.3mf`) au lieu du `model.stl` codé en dur actuellement ;
  le reste du rangement (dossier `<catégorie>/<nom>/`) ne change pas.
- `thumbnails.py` : si `f3d` échoue à générer une miniature pour un `.3mf` (format moins
  universellement supporté que le STL par les outils de rendu en ligne de commande),
  l'import du modèle ne doit pas échouer pour autant — `generate_thumbnail` doit retourner
  `None`/vide plutôt que lever, exactement comme un STL dont le rendu échouerait déjà
  aujourd'hui.
- `webapp.py` (`get_stl_file`) : le `media_type` passé à `FileResponse` est déterminé à partir
  de l'extension réelle du fichier servi (`model/stl` pour `.stl`, `model/3mf` pour `.3mf`) au
  lieu du `"model/stl"` fixe actuel, pour que le viewer Three.js et tout téléchargement direct
  reçoivent le bon type.

### 2. Script de déclenchement watcher

Nouveau fichier `3d/library/watch_trigger.py` (ou nom similaire) : petit script sans
dépendance lourde, appelé par le `.service` systemd, qui :

1. Liste les entrées de `~/3D`.
2. Si aucune n'est "mûre" (mtime > 10s), sort immédiatement (code 0).
3. Sinon, invoque `scanner.py --source ~/3D --library ~/3D_Library` (import direct de
   `scan_source`/`init_db`, pas de sous-process, pour rester simple).
4. Logge le résultat (stdout, capté par `journalctl --user -u 3d-library-watch.service`).

### 3. Unités systemd `--user`

- `~/.config/systemd/user/3d-library-watch.path` : `PathChanged=%h/3D` (ou
  `DirectoryNotEmpty=`), `Unit=3d-library-watch.service`.
- `~/.config/systemd/user/3d-library-watch.service` : `Type=oneshot`,
  `ExecStart=/usr/bin/python3 %h/Documents/Code/3d/library/watch_trigger.py`.
- Activation : `systemctl --user enable --now 3d-library-watch.path`. Fonctionne sans être
  root, tourne tant que la session utilisateur est active (standard sur un poste de bureau
  avec `loginctl enable-linger` si on veut que ça survive à la déconnexion — à activer aussi
  puisque l'utilisateur est sur un poste perso, pas un serveur).

## Migration / rattrapage initial (une seule fois, manuel avant d'activer le watcher)

1. Créer `~/Documents/FreeCAD/` s'il n'existe pas déjà pleinement utilisé comme tel.
2. Déplacer le contenu de `~/freecad-workspace/*` vers `~/Documents/FreeCAD/`.
3. Déplacer `~/3D/FFM_Trophy/`, `~/3D/DemoEquerre.FCStd` vers `~/Documents/FreeCAD/` (dossiers
   sources de travail — conserver ensemble le `.FCStd` et ses exports `.stl`/`.3mf` liés dans
   le même projet, pas dans `~/3D`).
4. Déplacer dans `~/3D` tout ce qui doit être catalogué et qui traîne encore ailleurs :
   fichiers `.zip`/`.stl`/`.3mf` non traités de `~/Téléchargements` (9 ZIP + 6 STL + les .3mf
   repérés), plus les exports déjà finis restés à plat dans `~/3D`
   (`Orsetto_Portachiavi.stl`, `porte_cle_42-*.3mf`, `Laptop-stand/*.stl` si le projet
   FreeCAD source correspondant n'existe pas/n'est plus actif).
5. Lancer une fois manuellement :
   `python3 scanner.py --source ~/3D --library ~/3D_Library`
   et vérifier le résumé (ajoutés/doublons/erreurs).
6. Activer les unités systemd (étape précédente) pour prendre le relais automatiquement.

## Gestion des erreurs

- Archive ZIP corrompue : déjà géré par `scanner.py` (`extract_zip` lève `ValueError`, le
  fichier reste en place pour inspection manuelle, erreur loggée en base `scan_log`) — inchangé.
- Fichier `.3mf` illisible par trimesh : traité comme une erreur d'import, au même titre
  qu'un STL cassé aujourd'hui — l'exception est catchée autour de l'analyse d'un fichier
  individuel (sans interrompre le reste du scan), le fichier reste dans `~/3D` pour inspection
  et sera retenté au prochain déclenchement du watcher.
- Le script `watch_trigger.py` ne doit jamais lever d'exception non catchée (sinon le service
  systemd part en échec et peut arrêter de redéclencher) : toute erreur est loggée, le script
  sort proprement.

## Tests / validation

- Déposer un `.zip` Thingiverse classique dans `~/3D`, vérifier dans `journalctl --user -u
  3d-library-watch.service -f` que le traitement se déclenche et que le modèle apparaît dans
  l'interface web sans action manuelle.
- Déposer un `.3mf` isolé, vérifier qu'il est catalogué avec dimensions/volume corrects.
- Déposer un fichier non pertinent (`.pdf`) dans `~/3D` : doit être ignoré sans erreur (rester
  en place, ou être explicitement signalé — comportement actuel de `scan_source` qui ne liste
  que `.zip`/`.stl`/`.3mf` à vérifier : les autres fichiers ne sont ni déplacés ni supprimés).
- Copier un gros fichier STL (plusieurs dizaines de Mo) et vérifier qu'il n'est pas traité
  avant la fin de l'écriture (débounce 10s respecté).
- `systemctl --user status 3d-library-watch.path` : confirmer "active (waiting)" en
  permanence, et absence de process Python résident (`ps aux | grep watch_trigger`) en dehors
  des déclenchements.

## Hors scope (explicitement exclu)

- Intégration OctoPrint (abandonnée pendant le brainstorming : le bouton OrcaSlicer existant
  est conservé tel quel).
- Recherche sémantique / IA locale (roadmap V3 de `docs/SPECS.md`), non demandée ici.
- Réorganisation plus profonde de `~/3D_Library` (structure des catégories) : hors scope, le
  comportement de rangement existant de `scanner.py` est conservé.
