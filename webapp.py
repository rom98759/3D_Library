"""
3D Library Manager - Interface web (V1)
Backend FastAPI : sert l'API REST + la page statique.

Usage:
    LIBRARY_DB_PATH=~/3D_Library/library.db python3 -m uvicorn webapp:app --reload
    (ou simplement : python3 webapp.py --library ~/3D_Library)
"""

import argparse
import os
import sqlite3
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = Path(os.environ.get("LIBRARY_DB_PATH", "library.db")).expanduser().resolve()

app = FastAPI(title="3D Library Manager")


def get_conn():
    if not DB_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Base introuvable : {DB_PATH}. Lance d'abord scanner.py.",
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
    conn = get_conn()
    row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Modèle introuvable")
    return dict(row)

@app.get("/api/models/{model_id}/thumbnail")
def get_thumbnail(model_id: int):
    thumbnail = DB_PATH.parent / "_thumbnails" / f"{model_id}.png"

    if not thumbnail.exists():
        raise HTTPException(status_code=404, detail="Thumbnail introuvable")

    return FileResponse(thumbnail)

@app.post("/api/models/{model_id}/open-folder")
def open_model_folder(model_id: int):
	"""Ouvre le dossier contenant le modèle dans l'explorateur de fichiers."""
	conn = get_conn()
	row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
	conn.close()
	if not row:
		raise HTTPException(status_code=404, detail="Modèle introuvable")

	model_path = Path(row["path"])
	if not model_path.exists():
		raise HTTPException(status_code=404, detail="Fichier du modèle introuvable")

	folder_path = model_path.parent
	if os.name == "nt":  # Windows
		os.startfile(folder_path)
	elif os.name == "posix":  # macOS / Linux
		import subprocess

		if sys.platform == "darwin":
			subprocess.run(["open", folder_path])
		else:
			subprocess.run(["xdg-open", folder_path])
	else:
		raise HTTPException(
			status_code=500, detail="Système d'exploitation non supporté"
		)

	return {"message": f"Dossier ouvert : {folder_path}"}

@app.post("/api/models/{model_id}/open-orcaslicer")
def open_model_in_orcaslicer(model_id: int):
	"""Ouvre le modèle dans OrcaSlicer."""
	conn = get_conn()
	row = conn.execute("SELECT * FROM models WHERE id = ?", (model_id,)).fetchone()
	conn.close()
	if not row:
		raise HTTPException(status_code=404, detail="Modèle introuvable")

	model_path = Path(row["path"])
	if not model_path.exists():
		raise HTTPException(status_code=404, detail="Fichier du modèle introuvable")

	# Commande pour ouvrir OrcaSlicer avec le fichier STL
	if os.name == "nt":  # Windows
		orcaslicer_executable = "C:\\Program Files\\OrcaSlicer\\OrcaSlicer.exe"
		os.startfile(f'"{orcaslicer_executable}" "{model_path}"')
	elif os.name == "posix":  # macOS / Linux
		import subprocess

		if sys.platform == "darwin":
			subprocess.run(["open", "-a", "OrcaSlicer", str(model_path)])
		else:
			subprocess.Popen([
				"flatpak",
				"run",
				"com.orcaslicer.OrcaSlicer",
				str(model_path)
			])
	else:
		raise HTTPException(
			status_code=500, detail="Système d'exploitation non supporté"
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
