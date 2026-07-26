"""
Miniatures - 3D Library Manager
Génère un rendu PNG d'un STL via F3D (rendu headless, avec ou sans
serveur X grâce à xvfb-run).

Prérequis système (Ubuntu) :
    sudo apt install f3d xvfb
"""

import shutil
import subprocess
from pathlib import Path

RESOLUTION = "500,500"
# Palette assortie au thème "plan technique" de l'interface web
BG_COLOR = "0.059,0.165,0.267"   # ~ #0F2A44
MODEL_COLOR = "0.91,0.94,0.95"

_XVFB_AVAILABLE = shutil.which("xvfb-run") is not None
_F3D_AVAILABLE = shutil.which("f3d") is not None


def _detect_bg_flag() -> str:
    """
    Le nom du flag de couleur de fond a changé entre versions de F3D
    (--bg-color sur les versions <= 2.x, --background-color sur les
    versions plus récentes). On détecte le bon flag une seule fois via
    `f3d --help` plutôt que de figer une version.
    """
    if not _F3D_AVAILABLE:
        return "--bg-color"
    try:
        result = subprocess.run(
            ["f3d", "--help"], capture_output=True, text=True, timeout=10
        )
        help_text = result.stdout + result.stderr
        if "--background-color" in help_text:
            return "--background-color"
    except Exception:
        pass
    return "--bg-color"


_BG_FLAG = _detect_bg_flag()


def f3d_is_available() -> bool:
    return _F3D_AVAILABLE


def generate_thumbnail(stl_path, output_png_path, timeout: int = 30) -> tuple[bool, str]:
    """
    Génère une miniature PNG pour le fichier STL donné.
    Retourne (succès, message).
    """
    if not _F3D_AVAILABLE:
        return False, "f3d n'est pas installé (sudo apt install f3d)"

    output_png_path = Path(output_png_path)
    output_png_path.parent.mkdir(parents=True, exist_ok=True)

    f3d_args = [
        "f3d", str(stl_path),
        f"--output={output_png_path}",
        f"--resolution={RESOLUTION}",
        f"{_BG_FLAG}={BG_COLOR}",
        f"--color={MODEL_COLOR}",
        "--edges",
        "--up=+Z",
        "--camera-azimuth-angle=35",
        "--camera-elevation-angle=20",
    ]

    # Sur un poste sans serveur X actif (script planifié, SSH sans -X, etc.),
    # xvfb-run fournit un display virtuel. Sur un bureau normal ça marche
    # aussi tout aussi bien, donc on l'utilise systématiquement si dispo.
    if _XVFB_AVAILABLE:
        cmd = ["xvfb-run", "-a"] + f3d_args
    else:
        cmd = f3d_args

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout ({timeout}s) lors du rendu de {stl_path}"

    if result.returncode != 0 or not output_png_path.exists():
        detail = (result.stderr or result.stdout or "").strip()[-400:]
        return False, f"Échec du rendu F3D : {detail}"

    return True, "OK"


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python3 thumbnails.py <fichier.stl> <sortie.png>")
        sys.exit(1)

    ok, msg = generate_thumbnail(sys.argv[1], sys.argv[2])
    print(msg if not ok else f"Miniature générée : {sys.argv[2]}")
    sys.exit(0 if ok else 1)
