"""
NB Tracker — detekcija zgrada po ključnim rečima u naslovu/opisu oglasa.
Zgrade: Wellport, West 65 Kula, West 65, Soul 64, Airport Garden, Zepterra,
        New Minel, A Blok, Bel Mondo, Belvil, Lastavica, Savada, The One,
        Pupinova palata, Kennedy Residence
"""

# Prioritet je bitan — duži/specifičniji match mora biti PRE kraćeg.
# Primer: "West 65 Kula" mora biti pre "West 65", inače kraći match uvek pobedi.
# Svaka zgrada: (display_name, [lista ključnih reči lowercase])
BUILDINGS = [
    # ── Specifičniji match pre opštijeg ───────────────────────────────
    ("West 65 Kula",   ["west 65 kula", "west65 kula", "west kula",
                         "west 65 tower", "west65 tower", "west tower"]),
    # ── Ostale zgrade po abecedi ──────────────────────────────────────
    ("A Blok",         ["a blok faza", "a-blok", "a blok"]),
    ("Airport Garden", ["airport garden"]),
    ("Bel Mondo",      ["bel mondo", "belmondo"]),
    ("Belvil",         ["belville", "belvil"]),
    ("Kennedy Residence", ["kennedy residence", "kennedy residences"]),
    ("Lastavica",      ["lastavica"]),
    ("New Minel",      ["new minel", "newminel", "novi minel"]),
    ("Pupinova palata",["pupinova palata"]),
    ("Savada",         ["savaada", "savada"]),
    ("Soul 64",        ["soul 64", "soul64", "soul"]),
    ("The One",        ["the one"]),
    ("Wellport",       ["wellport"]),
    ("West 65",        ["west 65", "west65"]),
    ("Zepterra",       ["zepterra", "zeptera"]),
]

# Nazivi koji se koriste u API responsu / JSON fajlovima
BUILDING_NAMES = [b[0] for b in BUILDINGS]


def detect_building(text: str) -> str | None:
    """
    Prima tekst (naslov + opis oglasa), vraća ime zgrade ili None.
    Pretraga je case-insensitive.
    """
    if not text:
        return None
    t = text.lower()
    for display_name, keywords in BUILDINGS:
        for kw in keywords:
            if kw in t:
                return display_name
    return None
