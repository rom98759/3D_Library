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


def purge_expired(conn: sqlite3.Connection, retention_days: int, now: datetime | None = None) -> list[int]:
    """Supprime (fichiers + ligne DB) les modèles en corbeille depuis plus de
    `retention_days` jours. Renvoie les ids effectivement purgés. Une erreur
    sur un item (fichiers déjà absents, erreur disque) est loguée et ignorée
    plutôt que de bloquer les suivants."""
    now = now or datetime.now()
    cutoff = now - timedelta(days=retention_days)
    rows = conn.execute(
        "SELECT id, path, deleted_at FROM models WHERE deleted_at IS NOT NULL"
    ).fetchall()

    purged = []
    for row in rows:
        if datetime.fromisoformat(row["deleted_at"]) > cutoff:
            continue
        try:
            folder = Path(row["path"]).parent
            if folder.exists():
                shutil.rmtree(folder)
        except OSError as e:
            print(f"[purge_trash] suppression fichiers échouée pour id={row['id']} : {e}", file=sys.stderr)
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
