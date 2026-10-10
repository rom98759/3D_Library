#!/usr/bin/env python3
"""
3D Library Manager - Purge de la corbeille
Appelé par le timer systemd `3d-library-purge.timer` (quotidien) : supprime
définitivement (fichiers + ligne DB) les modèles mis à la corbeille depuis
plus de TRASH_RETENTION_DAYS jours. Un item en échec (fichiers déjà absents,
erreur disque) ne doit jamais bloquer la purge des suivants.
"""

import os
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from scanner import init_db

DEFAULT_LIBRARY = Path("~/3D_Library").expanduser()
DEFAULT_RETENTION_DAYS = 30


def _retention_days_from_env() -> int:
    try:
        return int(os.environ.get("TRASH_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS)))
    except ValueError:
        return DEFAULT_RETENTION_DAYS


def _library_models_root(conn: sqlite3.Connection) -> Path:
    db_file = conn.execute("PRAGMA database_list").fetchone()[2]
    return (Path(db_file).parent / "models").resolve()


def _is_within_library_models(folder: Path, models_root: Path) -> bool:
    """True si `folder` est bien sous <bibliothèque>/models — jamais un
    chemin legacy ou inséré à la main qui pointerait ailleurs sur le disque
    (ex. un dossier source entier, voire /). N'autorise la suppression
    récursive que dans ce cas."""
    try:
        return folder.resolve().is_relative_to(models_root)
    except OSError:
        return False


def purge_expired(conn: sqlite3.Connection, retention_days: int, now: datetime | None = None) -> list[int]:
    """Supprime (fichiers + ligne DB) les modèles en corbeille depuis plus de
    `retention_days` jours. Renvoie les ids effectivement purgés.
    - Fichiers déjà absents : la ligne est purgée normalement.
    - Chemin hors de <bibliothèque>/models : la suppression de fichiers est
      ignorée (jamais de rmtree arbitraire), mais la ligne est purgée.
    - Échec disque réel (OSError, ex. permissions) : la ligne N'EST PAS
      purgée, pour retenter au prochain passage plutôt que perdre la trace
      de fichiers orphelins."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=retention_days)
    models_root = _library_models_root(conn)
    rows = conn.execute(
        "SELECT id, path, deleted_at FROM models WHERE deleted_at IS NOT NULL"
    ).fetchall()

    purged = []
    for row in rows:
        try:
            deleted_at = datetime.fromisoformat(row["deleted_at"])
        except ValueError:
            print(
                f"[purge_trash] deleted_at invalide pour id={row['id']} : {row['deleted_at']!r} — ignoré",
                file=sys.stderr,
            )
            continue
        if deleted_at > cutoff:
            continue

        folder = Path(row["path"]).parent
        if folder.exists():
            if not _is_within_library_models(folder, models_root):
                print(
                    f"[purge_trash] suppression fichiers ignorée (hors bibliothèque) "
                    f"pour id={row['id']} : {folder}",
                    file=sys.stderr,
                )
            else:
                try:
                    shutil.rmtree(folder)
                except OSError as e:
                    print(
                        f"[purge_trash] suppression fichiers échouée pour id={row['id']} : {e}",
                        file=sys.stderr,
                    )
                    continue  # échec réel : on retentera au prochain passage

        conn.execute("DELETE FROM models WHERE id = ?", (row["id"],))
        purged.append(row["id"])

    conn.commit()
    return purged


def main(library: Path = DEFAULT_LIBRARY, retention_days: int | None = None) -> int:
    retention_days = retention_days if retention_days is not None else _retention_days_from_env()
    db_path = library / "library.db"
    if not db_path.exists():
        print(f"[purge_trash] base introuvable : {db_path}", file=sys.stderr)
        return 0

    conn = init_db(db_path)
    conn.row_factory = sqlite3.Row
    try:
        purged = purge_expired(conn, retention_days)
        print(f"[purge_trash] {len(purged)} modèle(s) purgé(s) définitivement : {purged}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        # Ne jamais laisser une exception faire échouer le timer systemd :
        # on logue et on sort proprement, la prochaine exécution retentera.
        print(f"[purge_trash] erreur inattendue : {e}", file=sys.stderr)
        sys.exit(0)
