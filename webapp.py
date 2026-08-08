"""
3D Library Manager - Interface web
Backend FastAPI : sert l'API REST + la page statique.

Usage:
    LIBRARY_DB_PATH=~/3D_Library/library.db python3 -m uvicorn webapp:app --reload
    (ou simplement : python3 webapp.py --library ~/3D_Library)
"""

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB_PATH = Path(os.environ.get("LIBRARY_DB_PATH", "library.db")).expanduser().resolve()

# Commande pour lancer OrcaSlicer. Ajuste selon ton install :
#   - Linux (paquet/PATH) : orca-slicer
#   - Linux (Flatpak)     : flatpak run com.orcaslicer.OrcaSlicer
#   - Linux (AppImage)    : /chemin/vers/OrcaSlicer.AppImage
#   - macOS               : open -a OrcaSlicer   (géré automatiquement ci-dessous)
#   - Windows             : C:\Program Files\OrcaSlicer\OrcaSlicer.exe
ORCASLICER_CMD = os.environ.get("ORCASLICER_CMD", "flatpak run com.orcaslicer.OrcaSlicer")

app = FastAPI(title="3D Library Manager")


class ModelUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    material: str | None = None
    tags: str | None = None
    source_archive: str | None = None


def get_conn():
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Base introuvable : {DB_PATH}. Lance d'abord scanner.py.",
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_model_or_404(model_id: int) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    return dict(row)


@app.get("/api/models")
def list_models(q: str = "", category: str = ""):
    """Liste/recherche les modèles. Recherche simple sur le nom et les tags."""
    conn = get_conn()
    query = "SELECT * FROM models WHERE 1=1"
    params = []

    if q:
        query += " AND (name LIKE ? OR tags LIKE ? OR original_filename LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " ORDER BY added_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


@app.get("/api/models/{model_id}/stl")
def get_stl_file(model_id: int):
    """Sert le fichier STL brut, utilisé par le viewer 3D interactif (Three.js)."""
    model = get_model_or_404(model_id)
    stl_path = Path(model["path"])
    if not stl_path.exists():
        raise HTTPException(status_code=404, detail=f"Fichier STL introuvable : {stl_path}")
    return FileResponse(stl_path, media_type="model/stl")


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
    total = conn.execute("SELECT COUNT(*) AS c FROM models").fetchone()["c"]
    total_weight = conn.execute(
        "SELECT COALESCE(SUM(estimated_weight_g), 0) AS w FROM models"
    ).fetchone()["w"]
    total_time = conn.execute(
        "SELECT COALESCE(SUM(estimated_print_time_h), 0) AS t FROM models"
    ).fetchone()["t"]
    conn.close()
    return {
        "total_models": total,
        "total_weight_g": round(total_weight, 1),
        "total_print_time_h": round(total_time, 1),
    }


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", help="Dossier de la bibliothèque (contenant library.db)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.library:
        DB_PATH = Path(args.library).expanduser().resolve() / "library.db"

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)
