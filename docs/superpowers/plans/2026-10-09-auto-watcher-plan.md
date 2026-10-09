# 3D Library Manager — Auto-watcher & réorganisation des dossiers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Déclencher automatiquement le scan/catalogage de `~/3D` dès qu'un fichier y est déposé (zéro action manuelle, zéro process résident), ajouter le support `.3mf` manquant au scanner, et migrer les fichiers éparpillés vers la nouvelle organisation (`~/3D` = dépôt unique, `~/Documents/FreeCAD/` = projets actifs).

**Architecture:** Un `systemd --user path unit` (inotify noyau, aucun process entre deux dépôts) déclenche un `.service` `oneshot` qui lance `watch_trigger.py`. Ce script attend que les fichiers soient stables (pas modifiés depuis 10s) puis appelle `scanner.scan_source()`, déjà idempotent. `scanner.py` est étendu pour reconnaître `.3mf` en plus de `.stl` (seul et dans les ZIP), et `webapp.py` sert le bon `media_type` selon l'extension réelle.

**Tech Stack:** Python 3 (stdlib + trimesh/fastapi déjà en place), systemd `--user` units, pytest.

**Spec:** `docs/superpowers/specs/2026-10-09-auto-watcher-design.md`

## Global Constraints

- Aucun process résident entre deux dépôts de fichiers : le watcher est un `systemd --user path unit` (inotify), pas un daemon Python/`watchdog`.
- Débounce de 10 secondes minimum avant de traiter un fichier (évite de traiter un téléchargement/une copie en cours).
- `scanner.py` reste idempotent : ne jamais introduire de doublon en base même si le watcher se redéclenche plusieurs fois sur le même fichier.
- `watch_trigger.py` ne doit jamais laisser remonter une exception non catchée (le service systemd ne doit jamais passer en échec pour une erreur de contenu).
- Le bouton OrcaSlicer existant dans `webapp.py`/`static/index.html` n'est pas modifié ; OctoPrint est hors scope.
- La structure de rangement existante (`models/<catégorie>/<nom>/`, `_originals/`) n'est pas modifiée.

## Review Focus

- Un fichier encore en cours de téléchargement/copie (mtime très récent) est traité avant d'être complet → fichier tronqué catalogué ou doublon plus tard (couvert par Task 3, `test_watch_trigger.py`).
- Un `.3mf` isolé déposé dans `~/3D` n'est jamais catalogué (c'est la lacune d'origine de l'audit) (couvert par Task 1, `test_scanner_3mf.py`).
- Un `.3mf` à l'intérieur d'un ZIP n'est jamais catalogué (même lacune, chemin ZIP) (couvert par Task 1, `test_scanner_3mf.py`).
- Un `.3mf` corrompu/illisible par trimesh plante tout le scan au lieu d'être signalé et laissé en place (couvert par Task 1, `test_scanner_3mf.py`).
- Un fichier non pertinent (`.pdf`, `.gcode`, etc.) déposé dans `~/3D` est déplacé ou supprimé par erreur au lieu d'être simplement ignoré (couvert par Task 1, `test_scanner_3mf.py`).

---

## File Structure

- No change needed in `thumbnails.py` : `generate_thumbnail` échoue déjà de façon non bloquante
  (retourne `(False, message)` sans lever, quel que soit le format passé à `f3d`) — ce
  comportement couvre déjà le cas d'un rendu `.3mf` qui échouerait, exactement comme pour un
  `.stl` dont le rendu échouerait aujourd'hui. Pas de task dédiée.
- No change needed côté viewer Three.js (`static/index.html`) : `load3DViewer` catche déjà
  l'exception de `STLLoader` si le fichier n'est pas un STL valide et affiche un message
  d'erreur propre sans crasher la page — comportement déjà sûr pour un `.3mf` cliqué dans le
  viewer interactif. Pas de task dédiée.
- Modify `scanner.py` : `find_stl_files` reconnaît aussi `.3mf` ; le filtre des fichiers isolés dans `scan_source` inclut `.3mf` ; `insert_model` nomme le fichier final selon l'extension d'origine.
- Modify `webapp.py` : `get_stl_file` détermine le `media_type` à partir de l'extension réelle du fichier.
- Create `watch_trigger.py` : script appelé par le service systemd, débounce + appel à `scan_source`.
- Create `systemd/3d-library-watch.path` et `systemd/3d-library-watch.service` : unités `--user` versionnées dans le repo, à installer dans `~/.config/systemd/user/`.
- Create `tests/conftest.py`, `tests/test_scanner_3mf.py`, `tests/test_webapp_media_type.py`, `tests/test_watch_trigger.py`.

---

### Task 1: Support `.3mf` dans le scanner

**Files:**
- Modify: `scanner.py:155-157` (`find_stl_files`), `scanner.py:202` (`insert_model`), `scanner.py:328` (`scan_source`, boucle fichiers isolés)
- Test: `tests/conftest.py` (nouveau), `tests/test_scanner_3mf.py` (nouveau)

**Interfaces:**
- Consumes: rien de nouveau — mêmes signatures existantes `find_stl_files(directory) -> list[Path]`, `insert_model(conn, stl_path, source_archive, library_root) -> tuple[str|None, str]`, `scan_source(source, library_root, conn, delete_originals=False) -> dict`.
- Produces: `find_stl_files` retourne désormais aussi les `.3mf` ; `insert_model` nomme le fichier final `model<extension d'origine>` au lieu de toujours `model.stl` ; ces deux comportements sont réutilisés par `watch_trigger.py` (Task 3) via `scan_source`.

- [ ] **Step 1: Créer `tests/conftest.py` pour que les tests trouvent les modules du repo**

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 2: Écrire les tests (encore en échec) pour `find_stl_files`, `insert_model` et `scan_source`**

```python
# tests/test_scanner_3mf.py
import sqlite3
import zipfile
from pathlib import Path

import pytest

import scanner


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.executescript(scanner.DB_SCHEMA)
    yield connection
    connection.close()


def _patch_pipeline(monkeypatch, *, analysis_ok=True):
    """Isole scanner.py de trimesh/f3d : les tests ne valident pas le
    contenu réel des fichiers 3D, seulement la logique de routage par
    extension."""
    def fake_analyze_stl(path):
        if not analysis_ok:
            raise ValueError("fichier illisible")
        return {
            "size_x": 10.0, "size_y": 10.0, "size_z": 10.0,
            "volume": 1.0, "is_watertight": True, "material": "PLA",
            "estimated_weight_g": 1.0, "estimated_print_time_h": 0.1,
        }

    monkeypatch.setattr(scanner, "analyze_stl", fake_analyze_stl)
    monkeypatch.setattr(scanner, "auto_tag", lambda name, text: ("Atelier", ["test"]))
    monkeypatch.setattr(scanner, "f3d_is_available", lambda: False)


def test_find_stl_files_includes_3mf(tmp_path):
    (tmp_path / "a.stl").write_text("x")
    (tmp_path / "b.3mf").write_text("x")
    (tmp_path / "c.STL").write_text("x")
    (tmp_path / "d.3MF").write_text("x")
    (tmp_path / "e.pdf").write_text("x")

    found = {p.name for p in scanner.find_stl_files(tmp_path)}

    assert found == {"a.stl", "b.3mf", "c.STL", "d.3MF"}


def test_insert_model_names_file_by_extension(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch)
    library_root = tmp_path / "library"
    source_3mf = tmp_path / "Support batterie.3mf"
    source_3mf.write_text("fake 3mf content")

    name, status = scanner.insert_model(conn, source_3mf, None, library_root)

    assert name is not None, status
    row = conn.execute("SELECT path FROM models WHERE name = ?", (name,)).fetchone()
    assert row[0].endswith("model.3mf")
    assert Path(row[0]).exists()


def test_scan_source_processes_loose_3mf_and_leaves_unrelated_files(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch)
    source = tmp_path / "3D"
    source.mkdir()
    library_root = tmp_path / "library"
    (source / "piece.3mf").write_text("fake 3mf")
    (source / "notes.pdf").write_text("not a 3d file")

    stats = scanner.scan_source(source, library_root, conn)

    assert stats["added"] == 1
    assert stats["errors"] == 0
    # Le fichier non pertinent n'est ni déplacé ni supprimé.
    assert (source / "notes.pdf").exists()
    # Le fichier traité a quitté le dossier source (archivé dans _originals/).
    assert not (source / "piece.3mf").exists()
    assert (library_root / "_originals" / "piece.3mf").exists()


def test_scan_source_processes_3mf_inside_zip(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch)
    source = tmp_path / "3D"
    source.mkdir()
    library_root = tmp_path / "library"

    zpath = source / "thing_12345.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("model.3mf", "fake 3mf content")
        zf.writestr("README.txt", "info")

    stats = scanner.scan_source(source, library_root, conn)

    assert stats["added"] == 1
    assert stats["zips"] == 1
    assert stats["errors"] == 0
    rows = conn.execute("SELECT path FROM models").fetchall()
    assert rows[0][0].endswith("model.3mf")


def test_scan_source_corrupt_3mf_does_not_crash_whole_scan(tmp_path, conn, monkeypatch):
    _patch_pipeline(monkeypatch, analysis_ok=False)
    source = tmp_path / "3D"
    source.mkdir()
    library_root = tmp_path / "library"
    (source / "broken.3mf").write_text("not really a 3mf")

    stats = scanner.scan_source(source, library_root, conn)

    # analyze_stl échoue, mais insert_model catche déjà l'exception (comme
    # pour un STL cassé) : le modèle est quand même catalogué avec des
    # champs d'analyse vides, le scan ne plante pas.
    assert stats["errors"] == 0
    assert stats["added"] == 1
    row = conn.execute("SELECT size_x, is_watertight FROM models").fetchone()
    assert row == (None, None)
```

- [ ] **Step 3: Lancer les tests pour vérifier qu'ils échouent**

Run: `cd ~/Documents/Code/3d/library && python3 -m pytest tests/test_scanner_3mf.py -v`
Expected: FAIL — `find_stl_files` ne retourne pas les `.3mf`, `scan_source` ne traite pas les fichiers isolés `.3mf`, le fichier final est nommé `model.stl` même pour une source `.3mf`.

- [ ] **Step 4: Modifier `find_stl_files` pour inclure `.3mf`**

```python
def find_stl_files(directory: Path):
    """Trouve tous les fichiers .stl et .3mf dans un dossier, récursivement."""
    patterns = ["*.stl", "*.STL", "*.3mf", "*.3MF"]
    return [p for pattern in patterns for p in directory.rglob(pattern)]
```

- [ ] **Step 5: Modifier `insert_model` pour nommer le fichier final selon l'extension d'origine**

Remplacer dans `scanner.py` (ligne 202) :

```python
    target_stl = item_dir / "model.stl"
```

par :

```python
    target_stl = item_dir / f"model{stl_path.suffix.lower()}"
```

- [ ] **Step 6: Modifier `scan_source` pour traiter aussi les `.3mf` isolés**

Remplacer dans `scanner.py` (ligne 328) :

```python
        for stl in [f for f in all_files if f.suffix.lower() == ".stl"]:
```

par :

```python
        for stl in [f for f in all_files if f.suffix.lower() in (".stl", ".3mf")]:
```

- [ ] **Step 7: Relancer les tests pour vérifier qu'ils passent**

Run: `cd ~/Documents/Code/3d/library && python3 -m pytest tests/test_scanner_3mf.py -v`
Expected: PASS (5 tests)

- [ ] **Step 8: Vérifier que les tests existants ne régressent pas**

Run: `cd ~/Documents/Code/3d/library && python3 -m pytest -v`
Expected: PASS (tous les tests, y compris ceux des tasks suivantes une fois écrits)

- [ ] **Step 9: Commit**

```bash
git add scanner.py tests/conftest.py tests/test_scanner_3mf.py
git commit -m "feat(scanner): add .3mf support alongside .stl"
```

---

### Task 2: `media_type` correct selon l'extension dans `webapp.py`

**Files:**
- Modify: `webapp.py:132-139` (`get_stl_file`)
- Test: `tests/test_webapp_media_type.py` (nouveau)

**Interfaces:**
- Consumes: `get_model_or_404(model_id) -> dict` (déjà existant, inchangé), colonne `path` de la table `models`.
- Produces: `get_stl_file` sert toujours le fichier à `/api/models/{id}/stl`, mais avec `media_type="model/stl"` ou `media_type="model/3mf"` selon l'extension réelle.

- [ ] **Step 1: Écrire le test (encore en échec)**

```python
# tests/test_webapp_media_type.py
import sqlite3

from fastapi.testclient import TestClient

import scanner
import webapp


def _make_db(tmp_path):
    db_path = tmp_path / "library.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(scanner.DB_SCHEMA)

    stl_file = tmp_path / "model.stl"
    stl_file.write_bytes(b"fake stl content")
    mf_file = tmp_path / "model.3mf"
    mf_file.write_bytes(b"fake 3mf content")

    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (1, 'A', ?, '2026-01-01')",
        (str(stl_file),),
    )
    conn.execute(
        "INSERT INTO models (id, name, path, added_at) VALUES (2, 'B', ?, '2026-01-01')",
        (str(mf_file),),
    )
    conn.commit()
    conn.close()
    return db_path


def test_get_stl_file_media_type_by_extension(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(webapp, "DB_PATH", db_path)
    client = TestClient(webapp.app)

    stl_response = client.get("/api/models/1/stl")
    mf_response = client.get("/api/models/2/stl")

    assert stl_response.status_code == 200
    assert stl_response.headers["content-type"] == "model/stl"
    assert mf_response.status_code == 200
    assert mf_response.headers["content-type"] == "model/3mf"
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `cd ~/Documents/Code/3d/library && python3 -m pytest tests/test_webapp_media_type.py -v`
Expected: FAIL — les deux réponses ont `content-type: model/stl` (valeur fixe actuelle).

- [ ] **Step 3: Modifier `webapp.py`**

Ajouter, juste avant la fonction `get_stl_file` (après l'import `Path`) :

```python
def _media_type_for(path: Path) -> str:
    return "model/3mf" if path.suffix.lower() == ".3mf" else "model/stl"
```

Remplacer dans `get_stl_file` :

```python
    return FileResponse(stl_path, media_type="model/stl")
```

par :

```python
    return FileResponse(stl_path, media_type=_media_type_for(stl_path))
```

- [ ] **Step 4: Relancer le test pour vérifier qu'il passe**

Run: `cd ~/Documents/Code/3d/library && python3 -m pytest tests/test_webapp_media_type.py -v`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add webapp.py tests/test_webapp_media_type.py
git commit -m "fix(webapp): serve correct media_type for .3mf models"
```

---

### Task 3: `watch_trigger.py` — débounce + appel au scanner

**Files:**
- Create: `watch_trigger.py`
- Test: `tests/test_watch_trigger.py` (nouveau)

**Interfaces:**
- Consumes: `scanner.init_db(db_path) -> sqlite3.Connection`, `scanner.scan_source(source, library_root, conn, delete_originals=False) -> dict`.
- Produces: `has_stable_entries(source: Path, stable_seconds: int = 10) -> bool`, `main(source: Path = ..., library: Path = ...) -> int` (code de retour, utilisé comme point d'entrée `ExecStart` systemd dans Task 4).

- [ ] **Step 1: Écrire les tests (encore en échec)**

```python
# tests/test_watch_trigger.py
import os
import time
from pathlib import Path

import watch_trigger


def test_has_stable_entries_false_for_fresh_file(tmp_path):
    (tmp_path / "fresh.stl").write_text("x")

    assert watch_trigger.has_stable_entries(tmp_path, stable_seconds=10) is False


def test_has_stable_entries_true_once_old_enough(tmp_path):
    f = tmp_path / "old.stl"
    f.write_text("x")
    old_time = time.time() - 20
    os.utime(f, (old_time, old_time))

    assert watch_trigger.has_stable_entries(tmp_path, stable_seconds=10) is True


def test_main_skips_scan_when_nothing_stable(tmp_path, monkeypatch):
    source = tmp_path / "3D"
    source.mkdir()
    (source / "fresh.stl").write_text("x")
    library = tmp_path / "library"

    called = []
    monkeypatch.setattr(watch_trigger, "scan_source", lambda *a, **k: called.append(True))

    result = watch_trigger.main(source=source, library=library)

    assert result == 0
    assert called == []


def test_main_runs_scan_when_stable_file_present(tmp_path, monkeypatch):
    source = tmp_path / "3D"
    source.mkdir()
    f = source / "old.stl"
    f.write_text("x")
    old_time = time.time() - 20
    os.utime(f, (old_time, old_time))
    library = tmp_path / "library"

    calls = []
    monkeypatch.setattr(
        watch_trigger, "scan_source",
        lambda source, library_root, conn, **k: calls.append((source, library_root)) or {"added": 0},
    )

    result = watch_trigger.main(source=source, library=library)

    assert result == 0
    assert calls == [(source, library)]
    assert library.exists()  # init_db a bien créé le dossier bibliothèque


def test_main_returns_0_on_missing_source(tmp_path):
    missing = tmp_path / "does-not-exist"

    result = watch_trigger.main(source=missing, library=tmp_path / "library")

    assert result == 0
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `cd ~/Documents/Code/3d/library && python3 -m pytest tests/test_watch_trigger.py -v`
Expected: FAIL — `watch_trigger` n'existe pas encore (`ModuleNotFoundError`).

- [ ] **Step 3: Créer `watch_trigger.py`**

```python
#!/usr/bin/env python3
"""
3D Library Manager - Déclencheur du watcher
Appelé par le service systemd `3d-library-watch.service` à chaque
changement détecté par `3d-library-watch.path` (inotify) dans ~/3D.

N'exécute le scan que si au moins un fichier n'a pas été modifié depuis
STABLE_SECONDS : un téléchargement ou une copie encore en cours ne sera
traité qu'au prochain événement, une fois stabilisé.
"""

import sys
import time
from pathlib import Path

from scanner import init_db, scan_source

STABLE_SECONDS = 10
DEFAULT_SOURCE = Path("~/3D").expanduser()
DEFAULT_LIBRARY = Path("~/3D_Library").expanduser()


def has_stable_entries(source: Path, stable_seconds: int = STABLE_SECONDS) -> bool:
    """True si au moins un fichier de `source` n'a pas été modifié depuis
    `stable_seconds`. Ne regarde que les fichiers (pas les dossiers eux-mêmes)."""
    now = time.time()
    for entry in source.rglob("*"):
        if entry.is_file() and (now - entry.stat().st_mtime) >= stable_seconds:
            return True
    return False


def main(source: Path = DEFAULT_SOURCE, library: Path = DEFAULT_LIBRARY) -> int:
    if not source.exists():
        print(f"[watch_trigger] dossier source introuvable : {source}", file=sys.stderr)
        return 0

    if not has_stable_entries(source):
        print("[watch_trigger] rien de stable à traiter, on attend le prochain événement.")
        return 0

    library.mkdir(parents=True, exist_ok=True)
    conn = init_db(library / "library.db")
    try:
        stats = scan_source(source, library, conn)
        print(f"[watch_trigger] scan terminé : {stats}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Ne jamais laisser une exception faire échouer le service systemd :
        # on logge et on sort proprement, le prochain événement retentera.
        print(f"[watch_trigger] erreur inattendue : {e}", file=sys.stderr)
        sys.exit(0)
```

- [ ] **Step 4: Relancer les tests pour vérifier qu'ils passent**

Run: `cd ~/Documents/Code/3d/library && python3 -m pytest tests/test_watch_trigger.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Lancer toute la suite de tests**

Run: `cd ~/Documents/Code/3d/library && python3 -m pytest -v`
Expected: PASS (tous les tests des Tasks 1, 2 et 3)

- [ ] **Step 6: Commit**

```bash
git add watch_trigger.py tests/test_watch_trigger.py
git commit -m "feat(watcher): add debounced trigger script for the systemd path unit"
```

---

### Task 4: Unités systemd `--user` (watcher sans process résident)

**Files:**
- Create: `systemd/3d-library-watch.path`
- Create: `systemd/3d-library-watch.service`

**Interfaces:**
- Consumes: `watch_trigger.py` (Task 3), exécuté via `python3 %h/Documents/Code/3d/library/watch_trigger.py`.
- Produces: deux unités `systemd --user` installables, qui seront activées en Task 6.

- [ ] **Step 1: Créer `systemd/3d-library-watch.path`**

```ini
[Unit]
Description=Surveille ~/3D pour déclencher le scan automatique de la bibliothèque 3D

[Path]
PathChanged=%h/3D
Unit=3d-library-watch.service

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Créer `systemd/3d-library-watch.service`**

```ini
[Unit]
Description=Scan automatique de ~/3D (déclenché par 3d-library-watch.path)

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 %h/Documents/Code/3d/library/watch_trigger.py
```

- [ ] **Step 3: Vérifier que les fichiers sont syntaxiquement valides**

Run: `systemd-analyze --user verify ~/Documents/Code/3d/library/systemd/3d-library-watch.path ~/Documents/Code/3d/library/systemd/3d-library-watch.service 2>&1 || true`
Expected: pas d'erreur bloquante liée à la syntaxe (les unités ne sont pas encore installées, un avertissement de type "not found" sur le chemin standard est normal et sera résolu en Task 6 après symlink).

- [ ] **Step 4: Commit**

```bash
git add systemd/3d-library-watch.path systemd/3d-library-watch.service
git commit -m "feat(watcher): add systemd --user path/service units"
```

---

### Task 5: Migration — réorganisation des dossiers et rattrapage du stock existant

Tâche d'opération sur le système de fichiers de l'utilisateur (pas de code produit) : aucune
donnée n'est supprimée, uniquement déplacée. Chaque étape est vérifiée avant de passer à la
suivante.

**Files:** aucun fichier du repo — opérations sur `~/3D`, `~/3D_Library`, `~/Téléchargements`,
`~/freecad-workspace`, `~/Documents/FreeCAD`.

- [ ] **Step 1: Centraliser FreeCAD dans `~/Documents/FreeCAD/`**

```bash
mkdir -p ~/Documents/FreeCAD
mv ~/freecad-workspace/* ~/Documents/FreeCAD/
mv ~/3D/FFM_Trophy ~/Documents/FreeCAD/
mv ~/3D/DemoEquerre.FCStd ~/Documents/FreeCAD/
rmdir ~/freecad-workspace
```

Expected : `ls ~/freecad-workspace` échoue (dossier supprimé), `ls ~/Documents/FreeCAD`
contient `BoiteMuraleVis/`, `porte-cle-42/`, `poignee-babyfoot/`, `FFM_Trophy/`,
`DemoEquerre.FCStd`.

- [ ] **Step 2: Vérifier ce qu'il reste dans `~/3D` avant d'y ajouter le stock de `~/Téléchargements`**

Run: `find ~/3D -maxdepth 1`
Expected : seulement des fichiers déjà prêts à être catalogués (ex. `Orsetto_Portachiavi.stl`,
`Laptop-stand/`, `porte_cle_42-PorteCle42_Final.3mf`) — plus aucun `.FCStd`/`.FCBak`.

- [ ] **Step 3: Déplacer le stock non traité de `~/Téléchargements` vers `~/3D`**

```bash
mv ~/Téléchargements/*.zip ~/3D/ 2>/dev/null
mv ~/Téléchargements/*.stl ~/3D/ 2>/dev/null
mv ~/Téléchargements/*.3mf ~/3D/ 2>/dev/null
```

Expected : `find ~/3D -maxdepth 1 -iname "*.zip" -o -iname "*.stl" -o -iname "*.3mf" | wc -l`
reflète le total attendu (stock audité le 2026-10-09 : 9 zip + 6 stl + quelques 3mf, plus les
fichiers déjà présents dans `~/3D`).

- [ ] **Step 4: Lancer le scanner une fois, manuellement, pour repartir propre**

Run: `cd ~/Documents/Code/3d/library && python3 scanner.py --source ~/3D --library ~/3D_Library`
Expected : le résumé affiche `Erreurs : 0` (ou des erreurs explicables individuellement) et
`Modèles ajoutés` cohérent avec le nombre de fichiers déplacés à l'étape 3. Vérifier ensuite
`find ~/3D -maxdepth 1 -type f | wc -l` → doit être proche de 0 (seuls les sous-dossiers de
projets FreeCAD restants, s'il y en a, ou des fichiers en erreur explicitement signalés).

- [ ] **Step 5: Commit (rien à committer dans le repo — étape de documentation uniquement)**

Pas de commit git ici : cette tâche ne touche que le système de fichiers personnel de
l'utilisateur, hors du dépôt `3d/library`.

---

### Task 6: Activation du watcher et validation de bout en bout

**Files:** aucun fichier du repo modifié ; installation des unités créées en Task 4.

- [ ] **Step 1: Installer les unités systemd `--user`**

```bash
mkdir -p ~/.config/systemd/user
ln -sf ~/Documents/Code/3d/library/systemd/3d-library-watch.path ~/.config/systemd/user/3d-library-watch.path
ln -sf ~/Documents/Code/3d/library/systemd/3d-library-watch.service ~/.config/systemd/user/3d-library-watch.service
systemctl --user daemon-reload
```

- [ ] **Step 2: Activer le watcher et vérifier qu'il tourne sans process résident**

```bash
systemctl --user enable --now 3d-library-watch.path
loginctl enable-linger "$USER"
systemctl --user status 3d-library-watch.path --no-pager
```

Expected : `Active: active (waiting)`. Puis :

Run: `pgrep -af watch_trigger.py`
Expected : aucune sortie (aucun process résident entre deux dépôts).

- [ ] **Step 3: Test de bout en bout avec un fichier réel**

```bash
cp ~/Documents/Code/3d/library/docs/SPECS.md /tmp/fake_not_3d.pdf 2>/dev/null; true
cp /home/romain/3D_Library/_originals/music/*.stl /tmp/e2e_test_model.stl 2>/dev/null \
  || echo "solid e2e
endsolid e2e" > /tmp/e2e_test_model.stl
cp /tmp/e2e_test_model.stl ~/3D/e2e_test_model.stl
sleep 15
journalctl --user -u 3d-library-watch.service --since "1 minute ago" --no-pager
```

Expected : le journal montre `[watch_trigger] scan terminé : {...'added': 1...}` (ou un
`[ATTENTION] Analyse STL impossible` si le fichier de test est un STL minimal non valide pour
trimesh — dans ce cas le modèle est quand même catalogué avec des champs vides, ce qui reste un
succès du point de vue du watcher). Vérifier aussi :

Run: `find ~/3D -maxdepth 1 -iname "e2e_test_model.stl"`
Expected : aucune sortie — le fichier a bien été retiré de `~/3D` par le scanner déclenché
automatiquement, sans aucune action manuelle de l'utilisateur après le `cp`.

- [ ] **Step 4: Vérifier l'interface web**

Run: `cd ~/Documents/Code/3d/library && LIBRARY_DB_PATH=~/3D_Library/library.db python3 webapp.py --library ~/3D_Library &`
puis ouvrir `http://127.0.0.1:8000` et confirmer que le modèle `e2e_test_model` apparaît dans
la liste (recherche par nom), que sa fiche s'affiche sans erreur, et que le bouton OrcaSlicer
est toujours présent et fonctionne comme avant. Arrêter ensuite le serveur de test
(`kill %1` ou `Ctrl+C`).

- [ ] **Step 5: Commit final (mise à jour du changelog/README si besoin)**

Si un modèle `e2e_test_model` de test a été ajouté à la bibliothèque, le retirer proprement
depuis l'interface web ou directement en base avant de considérer la tâche terminée (c'était un
modèle de test, pas un vrai fichier à conserver) :

```bash
sqlite3 ~/3D_Library/library.db "DELETE FROM models WHERE name LIKE '%e2e%';"
```

Aucun commit git supplémentaire n'est nécessaire pour cette tâche (activation de service +
validation, pas de changement de code).
