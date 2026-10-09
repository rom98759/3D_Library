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
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import unicodedata
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
    print_count INTEGER DEFAULT 0,
    deleted_at TEXT,
    printed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_path TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    scanned_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_lists (
    model_id INTEGER NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    list_id INTEGER NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    PRIMARY KEY (model_id, list_id)
);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Crée les tables manquantes et ajoute les colonnes introduites après la
    création initiale de la base, sans toucher aux données existantes.
    Idempotent : peut être appelé à chaque démarrage (scanner, webapp,
    purge_trash)."""
    conn.executescript(DB_SCHEMA)  # CREATE TABLE IF NOT EXISTS : sûr à rejouer

    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(models)")}
    if "deleted_at" not in existing_cols:
        conn.execute("ALTER TABLE models ADD COLUMN deleted_at TEXT")
    if "printed" not in existing_cols:
        conn.execute("ALTER TABLE models ADD COLUMN printed INTEGER DEFAULT 0")
    conn.commit()

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


def slugify(text: str) -> str:
    """Nom de dossier propre : sans accents, minuscules, underscores."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "sans_nom"


def unique_item_dir(models_root: Path, category_slug: str, name_slug: str, file_hash: str) -> Path:
    """
    Résout le dossier final pour un modèle. En cas de collision de nom
    (deux fichiers différents qui se nettoient vers le même nom), on
    désambiguïse avec un court suffixe basé sur le hash du fichier.
    """
    base = models_root / category_slug / name_slug
    if not base.exists():
        return base

    candidate = models_root / category_slug / f"{name_slug}__{file_hash[:6]}"
    counter = 1
    while candidate.exists():
        candidate = models_root / category_slug / f"{name_slug}__{file_hash[:6]}_{counter}"
        counter += 1
    return candidate


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
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
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
    except RuntimeError as e:
        # Ex. archive protégée par mot de passe
        raise ValueError(f"Archive illisible (protégée par mot de passe ?) : {zip_path} ({e})")
    except NotImplementedError as e:
        # Ex. compression Deflate64 (Windows Explorer), non supportée par zipfile
        raise ValueError(f"Archive illisible (méthode de compression non supportée) : {zip_path} ({e})")

    return target_dir


def find_stl_files(directory: Path):
    """Trouve tous les fichiers .stl et .3mf dans un dossier, récursivement."""
    patterns = ["*.stl", "*.STL", "*.3mf", "*.3MF"]
    return [p for pattern in patterns for p in directory.rglob(pattern)]


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

    # Tags & catégorie automatiques (règles par mots-clés, cf. auto_tag.py).
    # Le nom de l'archive source porte souvent la seule indication de thème :
    # les STL issus de music.zip s'appellent "Billie Jean - Michael Jackson.stl",
    # aucun ne contient de mot-clé de catégorie. Sans l'archive dans le texte
    # analysé, ces modèles finissent tous en "Non classé".
    category, tags = auto_tag(name, f"{stl_path.name} {source_archive or ''}")
    tags_str = ",".join(tags)

    # --- Emplacement final organisé : models/<categorie>/<nom>/ ---
    models_root = library_root / "models"
    item_dir = unique_item_dir(models_root, slugify(category), slugify(name), h)
    item_dir.mkdir(parents=True, exist_ok=True)

    target_stl = item_dir / f"model{stl_path.suffix.lower()}"
    shutil.move(str(stl_path), str(target_stl))

    # Miniature (F3D), générée à côté du modèle. Non bloquant.
    thumb_path = None
    thumb_msg = ""
    if f3d_is_available():
        candidate_thumb = item_dir / "preview.png"
        ok, msg = generate_thumbnail(target_stl, candidate_thumb)
        if ok:
            thumb_path = candidate_thumb
        else:
            thumb_msg = f" (miniature non générée : {msg})"
    else:
        thumb_msg = " (f3d non installé : pas de miniature — voir README)"

    # metadata.json à côté du modèle, pour s'y retrouver même manuellement
    metadata = {
        "name": name,
        "original_filename": stl_path.name,
        "category": category,
        "tags": tags,
        "dimensions_mm": {
            "x": analysis["size_x"], "y": analysis["size_y"], "z": analysis["size_z"],
        },
        "volume_cm3": analysis["volume"],
        "is_watertight": analysis["is_watertight"],
        "material": analysis["material"],
        "estimated_weight_g": analysis["estimated_weight_g"],
        "estimated_print_time_h": analysis["estimated_print_time_h"],
        "source_archive": source_archive,
        "file_hash": h,
        "added_at": datetime.now().isoformat(),
    }
    (item_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    conn.execute(
        """INSERT INTO models
           (name, original_filename, path, file_hash, size_bytes, source_archive,
            category, tags, size_x, size_y, size_z, volume, is_watertight, material,
            estimated_weight_g, estimated_print_time_h, thumbnail_path, added_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            stl_path.name,
            str(target_stl.resolve()),
            h,
            size_bytes,
            source_archive,
            category, tags_str,
            analysis["size_x"], analysis["size_y"], analysis["size_z"],
            analysis["volume"], watertight_val, analysis["material"],
            analysis["estimated_weight_g"], analysis["estimated_print_time_h"],
            str(thumb_path.resolve()) if thumb_path else None,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()

    return name, f"Ajouté -> {item_dir.relative_to(library_root)}{thumb_msg}"


def consume_original(file_path: Path, source_root: Path, originals_root: Path, delete_originals: bool):
    """
    Retire le fichier source une fois traité : soit supprimé (--delete-originals),
    soit déplacé dans _originals/ (comportement par défaut, plus sûr) en
    conservant sa position relative au dossier source.
    """
    if delete_originals:
        file_path.unlink(missing_ok=True)
        return

    try:
        rel = file_path.relative_to(source_root)
    except ValueError:
        rel = Path(file_path.name)

    dest = originals_root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest = dest.with_name(f"{dest.stem}__{datetime.now().strftime('%H%M%S')}{dest.suffix}")
    shutil.move(str(file_path), str(dest))


def scan_source(source: Path, library_root: Path, conn: sqlite3.Connection, delete_originals: bool = False):
    """
    Parcourt le dossier source : extrait les ZIP, déplace chaque STL (issu
    d'un ZIP ou isolé) vers l'arborescence finale organisée. Le dossier
    source n'est qu'un point de passage : les fichiers traités en sont
    retirés (archivés dans _originals/ par défaut, ou supprimés).
    """
    originals_root = library_root / "_originals"
    stats = {"added": 0, "duplicates": 0, "errors": 0, "zips": 0}

    with tempfile.TemporaryDirectory(prefix="3dlib_extract_") as extract_tmp:
        extract_root = Path(extract_tmp)
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

                # ZIP entièrement traité : on le retire du dossier source
                consume_original(zpath, source, originals_root, delete_originals)

            except Exception as e:
                # Archive corrompue/chiffrée/non supportée, ou erreur inattendue
                # pendant le traitement de son contenu (disque, base...) : un seul
                # fichier problématique ne doit jamais interrompre tout le scan.
                # On laisse le ZIP en place pour inspection manuelle.
                print(f"  [ERREUR] {e}")
                log_scan(conn, str(zpath), "error", str(e))
                stats["errors"] += 1

        # 2. Traiter les STL isolés (hors ZIP)
        for stl in [f for f in all_files if f.suffix.lower() in (".stl", ".3mf")]:
            try:
                name, status = insert_model(conn, stl, None, library_root)
            except Exception as e:
                # Erreur inattendue (I/O, base...) : on laisse le fichier en
                # place pour inspection manuelle et on continue le scan.
                print(f"  [ERREUR] {stl.name} : {e}")
                log_scan(conn, str(stl), "error", str(e))
                stats["errors"] += 1
                continue

            if name:
                print(f"  [OK] {stl.name} -> {name} — {status}")
                stats["added"] += 1
            else:
                print(f"  [SKIP] {stl.name} : {status}")
                stats["duplicates"] += 1
                # Doublon : le fichier n'a pas été déplacé par insert_model,
                # on le retire quand même du dossier source (transit only)
                consume_original(stl, source, originals_root, delete_originals)

    return stats


def main():
    parser = argparse.ArgumentParser(description="3D Library Manager - Scanner V1")
    parser.add_argument("--source", required=True, help="Dossier à scanner (ex: ~/Downloads/3D)")
    parser.add_argument("--library", required=True, help="Dossier racine de la bibliothèque à créer/utiliser")
    parser.add_argument("--db-name", default="library.db", help="Nom du fichier SQLite (défaut: library.db)")
    parser.add_argument(
        "--delete-originals", action="store_true",
        help="Supprime définitivement les fichiers sources traités au lieu de les archiver dans _originals/",
    )
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

    stats = scan_source(source, library_root, conn, delete_originals=args.delete_originals)

    print("\n--- Résumé ---")
    print(f"Archives ZIP traitées : {stats['zips']}")
    print(f"Modèles ajoutés       : {stats['added']}")
    print(f"Doublons ignorés      : {stats['duplicates']}")
    print(f"Erreurs               : {stats['errors']}")

    conn.close()


if __name__ == "__main__":
    main()
