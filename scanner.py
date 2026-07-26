#!/usr/bin/env python3
"""
3D Library Manager - V1
Scanner de fichiers 3D : détecte les ZIP/STL dans un dossier source,
extrait les archives, nettoie les noms, et alimente une base SQLite.

Usage:
    python3 scanner.py --source ~/3D --library ~/3D_Library
"""

import argparse
import hashlib
import re
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

from stl_analysis import analyze_stl
from auto_tag import auto_tag
from thumbnails import generate_thumbnail, f3d_is_available

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    original_filename TEXT,
    path TEXT NOT NULL UNIQUE,
    file_hash TEXT UNIQUE,
    size_bytes INTEGER,
    source_archive TEXT,
    category TEXT,
    tags TEXT,
    size_x REAL,
    size_y REAL,
    size_z REAL,
    volume REAL,
    is_watertight INTEGER,
    material TEXT,
    estimated_weight_g REAL,
    estimated_print_time_h REAL,
    thumbnail_path TEXT,
    added_at TEXT NOT NULL,
    print_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_path TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    scanned_at TEXT NOT NULL
);
"""

# Bruit fréquent dans les noms de fichiers issus de Thingiverse / Printables / exports d'appareil photo
NOISE_PATTERNS = [
    r"^thingiverse[_\-]?",
    r"^thing[_\-]?\d+[_\-]?",
    r"^printables[_\-]?",
    r"^img[_\-]?\d{4,}",
    r"[_\-]?final[_\-]?v?\d*$",
    r"[_\-]?v\d+$",
    r"[_\-]?copy(\s*\(\d+\))?$",
    r"^\d{6,}[_\-]?",
]


def clean_name(raw_name: str) -> str:
    """Nettoie un nom de fichier brut en un nom lisible."""
    name = Path(raw_name).stem
    name = name.lower()

    for pattern in NOISE_PATTERNS:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE)

    name = re.sub(r"[_\-]+", " ", name).strip()
    name = re.sub(r"\s+", " ", name)

    if not name:
        name = Path(raw_name).stem  # fallback si tout a été nettoyé

    return name.capitalize()


def file_hash(path: Path, chunk_size: int = 65536) -> str:
    """Calcule un hash SHA-256 pour détecter les doublons."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(DB_SCHEMA)
    conn.commit()
    return conn


def log_scan(conn: sqlite3.Connection, path: str, status: str, detail: str = ""):
    conn.execute(
        "INSERT INTO scan_log (scanned_path, status, detail, scanned_at) VALUES (?, ?, ?, ?)",
        (path, status, detail, datetime.now().isoformat()),
    )
    conn.commit()


def extract_zip(zip_path: Path, extract_root: Path) -> Path:
    """Extrait un ZIP dans un sous-dossier dédié (nommé d'après l'archive)."""
    target_dir = extract_root / zip_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
    except zipfile.BadZipFile:
        raise ValueError(f"Archive corrompue ou invalide : {zip_path}")

    return target_dir


def find_stl_files(directory: Path):
    """Trouve tous les fichiers .stl dans un dossier, récursivement."""
    return list(directory.rglob("*.stl")) + list(directory.rglob("*.STL"))


def insert_model(conn: sqlite3.Connection, stl_path: Path, source_archive, library_root: Path):
    h = file_hash(stl_path)

    existing = conn.execute(
        "SELECT id, name FROM models WHERE file_hash = ?", (h,)
    ).fetchone()
    if existing:
        return None, f"Doublon détecté (déjà en base sous '{existing[1]}')"

    name = clean_name(stl_path.name)
    size_bytes = stl_path.stat().st_size

    # Analyse géométrique (dimensions, volume, poids/temps estimés)
    try:
        analysis = analyze_stl(stl_path)
    except Exception as e:
        # Un STL corrompu ou illisible ne doit pas bloquer tout le scan
        analysis = {
            "size_x": None, "size_y": None, "size_z": None,
            "volume": None, "is_watertight": None, "material": None,
            "estimated_weight_g": None, "estimated_print_time_h": None,
        }
        print(f"    [ATTENTION] Analyse STL impossible pour {stl_path.name} : {e}")

    watertight_val = (
        None if analysis["is_watertight"] is None
        else int(bool(analysis["is_watertight"]))
    )

    # Tags & catégorie automatiques (règles par mots-clés, cf. auto_tag.py)
    category, tags = auto_tag(name, stl_path.name)
    tags_str = ",".join(tags)

    cursor = conn.execute(
        """INSERT INTO models
           (name, original_filename, path, file_hash, size_bytes, source_archive,
            category, tags, size_x, size_y, size_z, volume, is_watertight, material,
            estimated_weight_g, estimated_print_time_h, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            stl_path.name,
            str(stl_path.resolve()),
            h,
            size_bytes,
            source_archive,
            category, tags_str,
            analysis["size_x"], analysis["size_y"], analysis["size_z"],
            analysis["volume"], watertight_val, analysis["material"],
            analysis["estimated_weight_g"], analysis["estimated_print_time_h"],
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    model_id = cursor.lastrowid

    # Miniature (F3D). Non bloquant : un échec de rendu n'empêche pas l'ajout.
    thumb_msg = ""
    if f3d_is_available():
        thumb_dir = library_root / "_thumbnails"
        thumb_path = thumb_dir / f"{model_id}.png"
        ok, msg = generate_thumbnail(stl_path, thumb_path)
        if ok:
            conn.execute(
                "UPDATE models SET thumbnail_path = ? WHERE id = ?",
                (str(thumb_path.resolve()), model_id),
            )
            conn.commit()
        else:
            thumb_msg = f" (miniature non générée : {msg})"
    else:
        thumb_msg = " (f3d non installé : pas de miniature — voir README)"

    return name, f"Ajouté{thumb_msg}"


def scan_source(source: Path, library_root: Path, conn: sqlite3.Connection):
    """Parcourt le dossier source : traite ZIP et STL isolés."""
    extract_root = library_root / "_extracted"
    extract_root.mkdir(parents=True, exist_ok=True)

    stats = {"added": 0, "duplicates": 0, "errors": 0, "zips": 0}

    all_files = list(source.rglob("*"))

    # 1. Traiter les ZIP
    for zpath in [f for f in all_files if f.suffix.lower() == ".zip"]:
        stats["zips"] += 1
        try:
            extracted_dir = extract_zip(zpath, extract_root)
            log_scan(conn, str(zpath), "extracted", str(extracted_dir))

            for stl in find_stl_files(extracted_dir):
                name, status = insert_model(conn, stl, zpath.name, library_root)
                if name:
                    print(f"  [OK] {zpath.name} -> {name} — {status}")
                    stats["added"] += 1
                else:
                    print(f"  [SKIP] {stl.name} : {status}")
                    stats["duplicates"] += 1

        except ValueError as e:
            print(f"  [ERREUR] {e}")
            log_scan(conn, str(zpath), "error", str(e))
            stats["errors"] += 1

    # 2. Traiter les STL isolés (hors ZIP)
    for stl in [f for f in all_files if f.suffix.lower() == ".stl"]:
        name, status = insert_model(conn, stl, None, library_root)
        if name:
            print(f"  [OK] {stl.name} -> {name} — {status}")
            stats["added"] += 1
        else:
            print(f"  [SKIP] {stl.name} : {status}")
            stats["duplicates"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="3D Library Manager - Scanner V1")
    parser.add_argument("--source", required=True, help="Dossier à scanner (ex: ~/Downloads/3D)")
    parser.add_argument("--library", required=True, help="Dossier racine de la bibliothèque à créer/utiliser")
    parser.add_argument("--db-name", default="library.db", help="Nom du fichier SQLite (défaut: library.db)")
    args = parser.parse_args()

    source = Path(args.source).expanduser().resolve()
    library_root = Path(args.library).expanduser().resolve()

    if not source.exists():
        print(f"Erreur : le dossier source n'existe pas : {source}", file=sys.stderr)
        sys.exit(1)

    library_root.mkdir(parents=True, exist_ok=True)
    db_path = library_root / args.db_name

    conn = init_db(db_path)

    print(f"Scan de : {source}")
    print(f"Bibliothèque : {library_root}")
    print(f"Base : {db_path}\n")

    stats = scan_source(source, library_root, conn)

    print("\n--- Résumé ---")
    print(f"Archives ZIP traitées : {stats['zips']}")
    print(f"Modèles ajoutés       : {stats['added']}")
    print(f"Doublons ignorés      : {stats['duplicates']}")
    print(f"Erreurs               : {stats['errors']}")

    conn.close()


if __name__ == "__main__":
    main()
