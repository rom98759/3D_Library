#!/usr/bin/env python3
"""
3D Library Manager - Déclencheur du watcher
Appelé par le service systemd `3d-library-watch.service` à chaque
changement détecté par `3d-library-watch.path` (inotify) dans ~/3D.

N'exécute le scan que si au moins un fichier n'a pas été modifié depuis
STABLE_SECONDS. Un `systemd --user path unit` ne se redéclenche que sur un
NOUVEL événement inotify : si un seul fichier est déposé et que rien
d'autre ne change ensuite dans ~/3D, aucun second événement n'arrivera
jamais. Le fichier doit donc être attendu DANS cette même exécution
(poll borné) plutôt que de compter sur un futur événement externe.
"""

import sys
import time
from pathlib import Path

from scanner import init_db, scan_source

STABLE_SECONDS = 10
POLL_INTERVAL_SECONDS = 2.0
MAX_POLLS = 6  # 6 x 2s = 12s d'attente bornée, au-delà des 10s de stabilité requis
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


def main(
    source: Path = DEFAULT_SOURCE,
    library: Path = DEFAULT_LIBRARY,
    stable_seconds: int = STABLE_SECONDS,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    max_polls: int = MAX_POLLS,
) -> int:
    if not source.exists():
        print(f"[watch_trigger] dossier source introuvable : {source}", file=sys.stderr)
        return 0

    attempts = 0
    while not has_stable_entries(source, stable_seconds) and attempts < max_polls:
        time.sleep(poll_interval)
        attempts += 1

    if not has_stable_entries(source, stable_seconds):
        print("[watch_trigger] rien n'est devenu stable dans le délai imparti, on abandonne.")
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
