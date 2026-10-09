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
