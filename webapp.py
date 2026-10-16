"""
3D Library Manager - Interface web
Backend FastAPI : sert l'API REST + la page statique.

Usage:
    LIBRARY_DB_PATH=~/3D_Library/library.db python3 -m uvicorn webapp:app --reload
    (ou simplement : python3 webapp.py --library ~/3D_Library)

Sous activation par socket systemd (3d-library-web.socket), le process est
lancé par systemd avec LISTEN_FDS=1 : on récupère le socket déjà ouvert (fd 3,
convention SD_LISTEN_FDS_START) au lieu d'écouter nous-mêmes, et on s'arrête
tout seul après IDLE_TIMEOUT_SECONDS d'inactivité — systemd relance
automatiquement le process à la prochaine connexion. Un lancement manuel
(sans LISTEN_FDS) n'est pas affecté : pas d'arrêt automatique.
"""

import argparse
import asyncio
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import scanner

DB_PATH = Path(os.environ.get("LIBRARY_DB_PATH", "library.db")).expanduser().resolve()
IDLE_TIMEOUT_SECONDS = int(os.environ.get("IDLE_TIMEOUT_SECONDS", "600"))
IDLE_CHECK_INTERVAL_SECONDS = 30.0
SD_LISTEN_FDS_START = 3  # convention systemd : premier socket passé = fd 3
TRASH_RETENTION_DAYS = int(os.environ.get("TRASH_RETENTION_DAYS", "30"))

SORT_COLUMNS = {
    "added_desc": "added_at DESC, id DESC",
    "added_asc": "added_at ASC, id DESC",
    "name_asc": "name COLLATE NOCASE ASC, id DESC",
    "name_desc": "name COLLATE NOCASE DESC, id DESC",
    "weight_desc": "estimated_weight_g DESC, id DESC",
    "weight_asc": "estimated_weight_g ASC, id DESC",
    "volume_desc": "volume DESC, id DESC",
    "volume_asc": "volume ASC, id DESC",
}


class ActivityTracker:
    """Suit l'instant de la dernière requête, pour savoir depuis combien de
    temps le serveur est inactif (utilisé par l'arrêt automatique)."""

    def __init__(self):
        self.last_activity = time.monotonic()

    def touch(self, now: float | None = None) -> None:
        self.last_activity = now if now is not None else time.monotonic()

    def idle_for(self, now: float | None = None) -> float:
        now = now if now is not None else time.monotonic()
        return now - self.last_activity


activity = ActivityTracker()


def listen_fd_count() -> int:
    """Nombre de sockets passés par systemd (LISTEN_FDS). 0 si lancé
    manuellement, ou si la variable est absente/invalide."""
    try:
        return int(os.environ.get("LISTEN_FDS", "0"))
    except ValueError:
        return 0


def uvicorn_run_kwargs(listen_fds: int, host: str, port: int) -> dict:
    """Arguments à passer à uvicorn.run() : le socket hérité de systemd s'il
    y en a un, sinon host/port classiques (lancement manuel)."""
    if listen_fds > 0:
        return {"fd": SD_LISTEN_FDS_START}
    return {"host": host, "port": port}


async def idle_shutdown_loop(
    tracker: ActivityTracker,
    timeout_seconds: float,
    check_interval: float = IDLE_CHECK_INTERVAL_SECONDS,
    max_iterations: int | None = None,
    on_shutdown=None,
) -> None:
    """
    Vérifie périodiquement si `tracker` est inactif depuis `timeout_seconds`
    et déclenche `on_shutdown` (par défaut : SIGTERM sur soi-même) le cas
    échéant, puis s'arrête. `max_iterations` et `on_shutdown` ne servent
    qu'aux tests — en production ils restent à leurs valeurs par défaut et
    la boucle tourne indéfiniment jusqu'à l'arrêt effectif du process.
    """
    if on_shutdown is None:
        def on_shutdown():
            os.kill(os.getpid(), signal.SIGTERM)

    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        await asyncio.sleep(check_interval)
        iterations += 1
        if tracker.idle_for() >= timeout_seconds:
            print(
                f"[webapp] inactif depuis {timeout_seconds:.0f}s, arrêt "
                "(sera relancé à la prochaine connexion par systemd).",
                flush=True,
            )
            on_shutdown()
            return


# Commande pour lancer OrcaSlicer. Ajuste selon ton install :
#   - Linux (paquet/PATH) : orca-slicer
#   - Linux (Flatpak)     : flatpak run com.orcaslicer.OrcaSlicer
#   - Linux (AppImage)    : /chemin/vers/OrcaSlicer.AppImage
#   - macOS               : open -a OrcaSlicer   (géré automatiquement ci-dessous)
#   - Windows             : C:\Program Files\OrcaSlicer\OrcaSlicer.exe
ORCASLICER_CMD = os.environ.get("ORCASLICER_CMD", "flatpak run com.orcaslicer.OrcaSlicer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Migre la base au démarrage : une bibliothèque de production existante
    # peut avoir été créée avant l'introduction de lists/model_lists/
    # deleted_at/printed. Sans cet appel, toute l'API renvoie 500 tant que
    # scanner.py n'a pas tourné au moins une fois.
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        scanner.ensure_schema(conn)
        conn.close()

    # L'arrêt automatique n'a de sens que sous activation par socket : un
    # lancement manuel (python3 webapp.py) n'a pas de systemd pour relancer
    # le process ensuite, donc on ne doit jamais s'y arrêter tout seul.
    if listen_fd_count() > 0:
        asyncio.create_task(idle_shutdown_loop(activity, IDLE_TIMEOUT_SECONDS))
    yield


app = FastAPI(title="3D Library Manager", lifespan=lifespan)


@app.middleware("http")
async def _track_activity(request, call_next):
    activity.touch()
    return await call_next(request)


class ModelUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    material: str | None = None
    tags: str | None = None
    source_archive: str | None = None
    printed: bool | None = None


class ListCreate(BaseModel):
    name: str


class ListRename(BaseModel):
    name: str


class ModelListsUpdate(BaseModel):
    list_ids: list[int]


class BatchAction(BaseModel):
    ids: list[int]
    action: Literal["trash", "restore", "delete", "add_list", "remove_list", "set_printed"]
    list_id: int | None = None
    printed: bool | None = None


def get_conn():
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Base introuvable : {DB_PATH}. Lance d'abord scanner.py.",
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _is_within_library_models(folder: Path) -> bool:
    """True si `folder` est bien sous <bibliothèque>/models — jamais un chemin
    legacy ou inséré à la main qui pointerait ailleurs sur le disque (ex. un
    dossier source entier, voire /). N'autorise la suppression récursive que
    dans ce cas."""
    models_root = (DB_PATH.parent / "models").resolve()
    try:
        return folder.resolve().is_relative_to(models_root)
    except OSError:
        return False


def _attach_lists(conn, models: list[dict]) -> None:
    if not models:
        return
    ids = [m["id"] for m in models]
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT ml.model_id AS model_id, l.id AS id, l.name AS name
            FROM model_lists ml
            JOIN lists l ON l.id = ml.list_id
            WHERE ml.model_id IN ({placeholders})
            ORDER BY l.name COLLATE NOCASE""",
        ids,
    ).fetchall()
    by_model: dict[int, list[dict]] = {}
    for r in rows:
        by_model.setdefault(r["model_id"], []).append({"id": r["id"], "name": r["name"]})
    for m in models:
        m["lists"] = by_model.get(m["id"], [])


def get_model_or_404(model_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    model = dict(row)
    _attach_lists(conn, [model])
    conn.close()
    return model


@app.get("/api/lists")
def get_lists():
    conn = get_conn()
    rows = conn.execute(
        """SELECT l.id, l.name,
                  (SELECT COUNT(*) FROM model_lists ml
                   JOIN models m ON m.id = ml.model_id
                   WHERE ml.list_id = l.id AND m.deleted_at IS NULL) AS model_count
           FROM lists l ORDER BY l.name COLLATE NOCASE"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/lists", status_code=201)
def create_list(data: ListCreate):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de liste requis")
    conn = get_conn()
    if conn.execute("SELECT id FROM lists WHERE name = ? COLLATE NOCASE", (name,)).fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Une liste avec ce nom existe déjà")
    cur = conn.execute(
        "INSERT INTO lists (name, created_at) VALUES (?, ?)",
        (name, datetime.now().isoformat()),
    )
    conn.commit()
    list_id = cur.lastrowid
    conn.close()
    return {"id": list_id, "name": name, "model_count": 0}


@app.put("/api/lists/{list_id}")
def rename_list(list_id: int, data: ListRename):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nom de liste requis")
    conn = get_conn()
    if not conn.execute("SELECT id FROM lists WHERE id = ?", (list_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Liste introuvable")
    if conn.execute(
        "SELECT id FROM lists WHERE name = ? COLLATE NOCASE AND id != ?", (name, list_id)
    ).fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Une liste avec ce nom existe déjà")
    conn.execute("UPDATE lists SET name = ? WHERE id = ?", (name, list_id))
    conn.commit()
    conn.close()
    return {"id": list_id, "name": name}


@app.delete("/api/lists/{list_id}")
def delete_list(list_id: int):
    conn = get_conn()
    if not conn.execute("SELECT id FROM lists WHERE id = ?", (list_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Liste introuvable")
    conn.execute("DELETE FROM lists WHERE id = ?", (list_id,))
    conn.commit()
    conn.close()
    return {"message": "Liste supprimée", "id": list_id}


@app.put("/api/models/{model_id}/lists")
def set_model_lists(model_id: int, data: ModelListsUpdate):
    get_model_or_404(model_id)
    conn = get_conn()
    valid_ids = {r["id"] for r in conn.execute("SELECT id FROM lists").fetchall()}
    requested = set(data.list_ids)
    unknown = requested - valid_ids
    if unknown:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Liste(s) inconnue(s) : {sorted(unknown)}")
    conn.execute("DELETE FROM model_lists WHERE model_id = ?", (model_id,))
    conn.executemany(
        "INSERT INTO model_lists (model_id, list_id) VALUES (?, ?)",
        [(model_id, lid) for lid in requested],
    )
    conn.commit()
    conn.close()
    return {"model_id": model_id, "list_ids": sorted(requested)}


@app.post("/api/models/{model_id}/trash")
def trash_model(model_id: int):
    get_model_or_404(model_id)
    conn = get_conn()
    conn.execute(
        "UPDATE models SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
        (datetime.now().isoformat(), model_id),
    )
    conn.commit()
    conn.close()
    return {"message": "Modèle mis à la corbeille", "id": model_id}


@app.post("/api/models/{model_id}/restore")
def restore_model(model_id: int):
    get_model_or_404(model_id)
    conn = get_conn()
    conn.execute("UPDATE models SET deleted_at = NULL WHERE id = ?", (model_id,))
    conn.commit()
    conn.close()
    return {"message": "Modèle restauré", "id": model_id}


@app.delete("/api/models/{model_id}")
def delete_model(model_id: int):
    model = get_model_or_404(model_id)
    conn = get_conn()
    conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
    conn.commit()
    conn.close()

    folder = Path(model["path"]).parent
    if folder.exists() and _is_within_library_models(folder):
        try:
            shutil.rmtree(folder)
        except OSError as e:
            print(f"[webapp] suppression fichiers échouée pour id={model_id} : {e}")
    elif folder.exists():
        print(f"[webapp] suppression fichiers ignorée (hors bibliothèque) pour id={model_id} : {folder}")
    return {"message": "Modèle supprimé définitivement", "id": model_id}


@app.post("/api/models/batch")
def batch_action(data: BatchAction):
    conn = get_conn()

    if data.action in ("add_list", "remove_list"):
        if data.list_id is None:
            conn.close()
            raise HTTPException(status_code=400, detail="list_id requis pour cette action")
        if not conn.execute("SELECT id FROM lists WHERE id = ?", (data.list_id,)).fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Liste introuvable")
    if data.action == "set_printed" and data.printed is None:
        conn.close()
        raise HTTPException(status_code=400, detail="printed requis pour cette action")

    unique_ids = list(dict.fromkeys(data.ids))  # dédoublonne en gardant l'ordre

    existing_ids = set()
    if unique_ids:
        placeholders = ",".join("?" * len(unique_ids))
        existing_ids = {
            r["id"] for r in conn.execute(
                f"SELECT id FROM models WHERE id IN ({placeholders})", unique_ids,
            ).fetchall()
        }

    processed, skipped = [], []
    folders_to_remove = []  # supprimés sur disque seulement après le commit final
    for model_id in unique_ids:
        if model_id not in existing_ids:
            skipped.append(model_id)
            continue

        if data.action == "trash":
            conn.execute(
                "UPDATE models SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                (datetime.now().isoformat(), model_id),
            )
        elif data.action == "restore":
            conn.execute("UPDATE models SET deleted_at = NULL WHERE id = ?", (model_id,))
        elif data.action == "delete":
            row = conn.execute("SELECT path FROM models WHERE id = ?", (model_id,)).fetchone()
            conn.execute("DELETE FROM models WHERE id = ?", (model_id,))
            if row:
                folders_to_remove.append(Path(row["path"]).parent)
        elif data.action == "add_list":
            conn.execute(
                "INSERT OR IGNORE INTO model_lists (model_id, list_id) VALUES (?, ?)",
                (model_id, data.list_id),
            )
        elif data.action == "remove_list":
            conn.execute(
                "DELETE FROM model_lists WHERE model_id = ? AND list_id = ?",
                (model_id, data.list_id),
            )
        elif data.action == "set_printed":
            conn.execute(
                "UPDATE models SET printed = ? WHERE id = ?",
                (1 if data.printed else 0, model_id),
            )
        processed.append(model_id)

    conn.commit()
    conn.close()

    for folder in folders_to_remove:
        if folder.exists() and _is_within_library_models(folder):
            try:
                shutil.rmtree(folder)
            except OSError as e:
                print(f"[webapp] suppression fichiers échouée pour {folder} : {e}")
        elif folder.exists():
            print(f"[webapp] suppression fichiers ignorée (hors bibliothèque) : {folder}")

    return {"processed": processed, "skipped": skipped}


@app.get("/api/trash")
def list_trash():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM models WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
    ).fetchall()
    models = [dict(r) for r in rows]
    _attach_lists(conn, models)
    conn.close()
    for m in models:
        try:
            purge_at = datetime.fromisoformat(m["deleted_at"]) + timedelta(days=TRASH_RETENTION_DAYS)
            m["purge_at"] = purge_at.isoformat()
        except ValueError:
            m["purge_at"] = None
    return models


@app.get("/api/models")
def list_models(q: str = "", category: str = "", lists: str = "", printed: str = "", sort: str = "added_desc"):
    """Liste/recherche les modèles actifs (non supprimés), avec filtres combinés."""
    conn = get_conn()
    query = "SELECT * FROM models WHERE deleted_at IS NULL"
    params = []

    if q:
        query += " AND (name LIKE ? ESCAPE '\\' OR tags LIKE ? ESCAPE '\\' OR original_filename LIKE ? ESCAPE '\\')"
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        params += [like, like, like]

    if category:
        query += " AND category = ?"
        params.append(category)

    if lists:
        for list_id_str in lists.split(","):
            list_id_str = list_id_str.strip()
            if not (list_id_str.isascii() and list_id_str.isdigit()):
                continue
            query += " AND id IN (SELECT model_id FROM model_lists WHERE list_id = ?)"
            params.append(int(list_id_str))

    if printed in ("true", "false"):
        query += " AND printed = ?"
        params.append(1 if printed == "true" else 0)

    query += " ORDER BY " + SORT_COLUMNS.get(sort, SORT_COLUMNS["added_desc"])

    rows = conn.execute(query, params).fetchall()
    models = [dict(r) for r in rows]
    _attach_lists(conn, models)
    conn.close()
    return models


@app.get("/api/models/{model_id}")
def get_model(model_id: int):
    return get_model_or_404(model_id)


@app.put("/api/models/{model_id}")
def update_model(model_id: int, data: ModelUpdate):
    conn = get_conn()

    model = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    if not model:
        conn.close()
        raise HTTPException(status_code=404, detail="Modèle introuvable")

    fields, values = [], []
    for key, value in data.model_dump().items():
        if value is not None:
            fields.append(f"{key} = ?")
            values.append(value)

    if fields:
        values.append(model_id)
        query = f"UPDATE models SET {', '.join(fields)} WHERE id = ?"
        conn.execute(query, values)
        conn.commit()

    conn.close()
    return {"message": "Modèle modifié", "id": model_id}


@app.get("/api/models/{model_id}/thumbnail")
def get_thumbnail(model_id: int):
    """
    Sert la miniature du modèle. Le chemin réel est stocké en base
    (thumbnail_path), à côté du model.stl dans models/<categorie>/<nom>/preview.png
    — ne pas reconstruire un chemin à partir de l'id, ça ne correspond plus
    à l'arborescence depuis la réorganisation du scanner.
    """
    model = get_model_or_404(model_id)
    thumb = model.get("thumbnail_path")
    if not thumb or not Path(thumb).exists():
        raise HTTPException(status_code=404, detail="Miniature introuvable pour ce modèle")
    return FileResponse(thumb, media_type="image/png")


def _media_type_for(path: Path) -> str:
    return "model/3mf" if path.suffix.lower() == ".3mf" else "model/stl"


@app.get("/api/models/{model_id}/stl")
def get_stl_file(model_id: int):
    """Sert le fichier STL/3MF brut, utilisé par le viewer 3D interactif (Three.js)."""
    model = get_model_or_404(model_id)
    stl_path = Path(model["path"])
    if not stl_path.exists():
        raise HTTPException(status_code=404, detail=f"Fichier STL introuvable : {stl_path}")
    return FileResponse(stl_path, media_type=_media_type_for(stl_path))


@app.post("/api/models/{model_id}/open-folder")
def open_model_folder(model_id: int):
    """Ouvre le dossier contenant le modèle dans l'explorateur de fichiers."""
    model = get_model_or_404(model_id)
    model_path = Path(model["path"])
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Fichier du modèle introuvable : {model_path}")

    folder_path = model_path.parent

    try:
        if os.name == "nt":
            os.startfile(folder_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(folder_path)], check=True)
        else:
            opener = shutil.which("xdg-open")
            if not opener:
                raise HTTPException(status_code=500, detail="xdg-open introuvable sur ce système")
            subprocess.Popen([opener, str(folder_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Impossible d'ouvrir le dossier : {e}")

    return {"message": f"Dossier ouvert : {folder_path}", "folder": str(folder_path)}


@app.post("/api/models/{model_id}/open-orcaslicer")
def open_model_in_orcaslicer(model_id: int):
    """Ouvre le modèle dans OrcaSlicer."""
    model = get_model_or_404(model_id)
    model_path = Path(model["path"])
    if not model_path.exists():
        raise HTTPException(status_code=404, detail=f"Fichier du modèle introuvable : {model_path}")

    try:
        if os.name == "nt":
            orcaslicer_executable = os.environ.get(
                "ORCASLICER_CMD", r"C:\Program Files\OrcaSlicer\OrcaSlicer.exe"
            )
            subprocess.Popen([orcaslicer_executable, str(model_path)])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-a", "OrcaSlicer", str(model_path)], check=True)
        else:
            cmd = ORCASLICER_CMD.split() + [str(model_path)]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Commande introuvable : '{ORCASLICER_CMD}'. "
                "Ajuste la variable d'environnement ORCASLICER_CMD selon ton installation "
                "(paquet/PATH, flatpak run com.orcaslicer.OrcaSlicer, AppImage, etc.)."
            ),
        )

    return {"message": f"OrcaSlicer ouvert avec le modèle : {model_path}"}


@app.get("/api/stats")
def get_stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) AS c FROM models WHERE deleted_at IS NULL").fetchone()["c"]
    total_weight = conn.execute(
        "SELECT COALESCE(SUM(estimated_weight_g), 0) AS w FROM models WHERE deleted_at IS NULL"
    ).fetchone()["w"]
    total_time = conn.execute(
        "SELECT COALESCE(SUM(estimated_print_time_h), 0) AS t FROM models WHERE deleted_at IS NULL"
    ).fetchone()["t"]
    trash_count = conn.execute(
        "SELECT COUNT(*) AS c FROM models WHERE deleted_at IS NOT NULL"
    ).fetchone()["c"]
    recent_rows = conn.execute(
        "SELECT * FROM models WHERE deleted_at IS NULL ORDER BY added_at DESC LIMIT 5"
    ).fetchall()
    recent = [dict(r) for r in recent_rows]
    _attach_lists(conn, recent)
    conn.close()
    return {
        "total_models": total,
        "total_weight_g": round(total_weight, 1),
        "total_print_time_h": round(total_time, 1),
        "trash_count": trash_count,
        "recent": recent,
    }


FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"


@app.get("/")
def index():
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.exists():
        raise HTTPException(
            status_code=500,
            detail=(
                "Frontend non buildé : lance `cd frontend && npm install && npm run build`, "
                "puis relance webapp.py."
            ),
        )
    return FileResponse(index_file)


# Gardé conditionnel : frontend/dist est ignoré par git (cf. .gitignore), donc
# absent sur un clone frais tant que `npm run build` n'a pas tourné une fois.
# StaticFiles lève une RuntimeError à la construction si le dossier n'existe
# pas, ce qui casserait l'import de webapp.py (et donc toute la suite de
# tests) sans ce garde-fou.
if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", help="Dossier de la bibliothèque (contenant library.db)")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.library:
        DB_PATH = Path(args.library).expanduser().resolve() / "library.db"

    import uvicorn
    uvicorn.run(app, **uvicorn_run_kwargs(listen_fd_count(), "127.0.0.1", args.port))
