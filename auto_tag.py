"""
Tags automatiques - 3D Library Manager
Catégorisation par mots-clés (FR/EN) à partir du nom nettoyé et du nom de fichier
d'origine. Volontairement simple (règles), sans dépendance IA — l'étape V3
(Ollama + recherche sémantique) pourra s'appuyer dessus ou la remplacer.
"""

import re

# Catégorie -> mots-clés associés (FR + EN, les termes Thingiverse sont
# très souvent en anglais même pour des créateurs francophones)
CATEGORY_KEYWORDS = {
    "Atelier": [
        "atelier",
        "tool",
        "outil",
        "tournevis",
        "screwdriver",
        "wrench",
        "cle",
        "clé",
        "perceuse",
        "drill",
        "etabli",
        "établi",
        "visserie",
        "vis",
        "screw",
        "bit holder",
        "tool holder",
        "workshop",
    ],
    "Robotique": [
        "robot",
        "robotique",
        "servo",
        "esp32",
        "esp8266",
        "arduino",
        "raspberry",
        "rpi",
        "chassis",
        "châssis",
        "moteur",
        "motor",
        "capteur",
        "sensor",
        "drone",
        "rc car",
        "stepper",
    ],
    "Électronique": [
        "boitier",
        "boîtier",
        "enclosure",
        "case",
        "pcb",
        "cable",
        "câble",
        "connecteur",
        "connector",
        "battery",
        "batterie",
        "phone stand",
        "support telephone",
        "support téléphone",
        "camera",
        "caméra",
        "raspberry pi case",
    ],
    "Maison": [
        "crochet",
        "hook",
        "meuble",
        "furniture",
        "mural",
        "wall mount",
        "wall",
        "cuisine",
        "kitchen",
        "salle de bain",
        "bathroom",
        "rangement",
        "storage",
        "organizer",
        "organiseur",
        "decor",
        "décor",
        "lampe",
        "lamp",
        "porte",
        "door",
        "tiroir",
        "drawer",
    ],
    "Pièces techniques": [
        "adaptateur",
        "adapter",
        "entretoise",
        "spacer",
        "bride",
        "clamp",
        "engrenage",
        "gear",
        "bracket",
        "support technique",
        "joint",
        "raccord",
        "fitting",
        "piece",
        "pièce",
        "rondelle",
        "washer",
        "ecrou",
        "écrou",
        "nut",
    ],
    "Musique": [
        "instrument",
        "musique",
        "music",
        "guitar",
        "piano",
        "violin",
        "flute",
        "drum",
        "saxophone",
        "trumpet",
        "clarinet",
        "cello",
        "trombone",
        "bass",
        "ukulele",
        "harmonica",
        "accordion",
        "banjo",
        "oboe",
        "tuba",
        "percussion",
    ],
}

# Mots-clés génériques ajoutés comme tags même s'ils ne déterminent pas
# la catégorie (permet une recherche plus fine)
EXTRA_TAG_KEYWORDS = [
    "holder",
    "support",
    "stand",
    "mount",
    "case",
    "cover",
    "clip",
    "hinge",
    "charniere",
    "charnière",
    "box",
    "boite",
    "boîte",
]

DEFAULT_CATEGORY = "Non classé"


def _normalize(text: str) -> str:
    return re.sub(r"[_\-]+", " ", text.lower())


def auto_tag(cleaned_name: str, original_filename: str = "") -> tuple[str, list[str]]:
    """
    Détermine une catégorie et une liste de tags à partir du nom nettoyé
    et, en complément, du nom de fichier d'origine.

    Retourne (category, tags). category = "Non classé" si aucun mot-clé
    ne correspond.
    """
    haystack = _normalize(f"{cleaned_name} {original_filename}")

    matched_category = DEFAULT_CATEGORY
    tags = set()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in haystack:
                tags.add(kw.replace(" ", "_"))
                if matched_category == DEFAULT_CATEGORY:
                    matched_category = category

    for kw in EXTRA_TAG_KEYWORDS:
        if kw in haystack:
            tags.add(kw.replace(" ", "_"))

    return matched_category, sorted(tags)


if __name__ == "__main__":
    import sys

    name = sys.argv[1] if len(sys.argv) > 1 else "Support batterie"
    original = sys.argv[2] if len(sys.argv) > 2 else ""
    cat, tags = auto_tag(name, original)
    print(f"Catégorie : {cat}")
    print(f"Tags      : {', '.join(tags) if tags else '(aucun)'}")
