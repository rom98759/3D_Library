"""
Analyse STL - 3D Library Manager
Extrait dimensions, volume, poids estimé (PLA) et une estimation grossière
du temps d'impression à partir d'un fichier STL.
"""

import trimesh

# Densités courantes (g/cm3) pour l'estimation de poids
MATERIAL_DENSITIES = {
    "PLA": 1.24,
    "PETG": 1.27,
    "ABS": 1.04,
    "TPU": 1.21,
    "ASA": 1.07,
}

DEFAULT_MATERIAL = "PLA"

# Débit volumique approximatif (cm3/h) pour une impression FDM "standard"
# (buse 0.4mm, vitesse modérée, infill ~15-20%). Très approximatif :
# une estimation fiable nécessite un vrai slicer (hauteur de couche,
# vitesse, infill réel, supports, etc.)
APPROX_PRINT_RATE_CM3_PER_HOUR = 15.0

# Ratio moyen matière réellement extrudée / volume plein du modèle,
# pour tenir compte d'un infill typique (~15-20%) + parois.
# Sert uniquement à l'estimation de poids, pas au volume affiché
# (le volume affiché reste le volume géométrique plein du mesh).
DEFAULT_INFILL_RATIO = 0.35


def analyze_stl(stl_path, material: str = DEFAULT_MATERIAL) -> dict:
    """
    Analyse un fichier STL et retourne un dict avec :
    - size_x, size_y, size_z (mm)
    - volume (cm3, volume géométrique plein du modèle)
    - is_watertight (bool) : indique si le volume est fiable
    - estimated_weight_g (g, estimation avec infill approx.)
    - estimated_print_time_h (heures, estimation grossière)
    - material

    Lève une exception si le fichier ne peut pas être chargé.
    """
    mesh = trimesh.load(str(stl_path), force="mesh")

    # Dimensions (bounding box), en mm (convention STL standard)
    bounds = mesh.bounding_box.extents  # [x, y, z]
    size_x, size_y, size_z = (round(float(v), 2) for v in bounds)

    is_watertight = bool(mesh.is_watertight)

    # Volume géométrique (mm3 -> cm3). Fiable seulement si le mesh est "watertight"
    # (fermé). Sinon trimesh peut renvoyer une valeur incohérente (parfois négative).
    if is_watertight:
        volume_mm3 = abs(float(mesh.volume))
    else:
        # Fallback : volume de la bounding box, très grossier, signalé comme tel
        volume_mm3 = size_x * size_y * size_z

    volume_cm3 = round(volume_mm3 / 1000.0, 2)

    density = MATERIAL_DENSITIES.get(material.upper(), MATERIAL_DENSITIES[DEFAULT_MATERIAL])
    estimated_weight_g = round(volume_cm3 * density * DEFAULT_INFILL_RATIO, 1)

    estimated_print_time_h = round(
        (volume_cm3 * DEFAULT_INFILL_RATIO) / APPROX_PRINT_RATE_CM3_PER_HOUR, 2
    )

    return {
        "size_x": size_x,
        "size_y": size_y,
        "size_z": size_z,
        "volume": volume_cm3,
        "is_watertight": is_watertight,
        "material": material.upper(),
        "estimated_weight_g": estimated_weight_g,
        "estimated_print_time_h": estimated_print_time_h,
    }


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 stl_analysis.py <fichier.stl>")
        sys.exit(1)

    result = analyze_stl(sys.argv[1])
    for key, value in result.items():
        print(f"{key}: {value}")
