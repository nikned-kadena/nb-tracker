"""
NB Tracker — detekcija zgrada po ključnim rečima u naslovu/opisu oglasa.
Zgrade: Wellport, West 65 Kula, West 65, Soul 64, Airport Garden, Zepterra,
        New Minel, A Blok, Bel Mondo, Belvil, Lastavica, Savada, The One,
        Pupinova palata, Kennedy Residence, Sakura Park, Elixir Garden

v2 (08.07.2026) — sistemske popravke posle projekta procene vrednosti:
  1. BLACKLIST: nesrodni blokovi/naselja (Ledine, Blok 45+, Zemun...) → None
  2. Naslov ima veći prioritet od opisa (ako naslov jasno pogađa zgradu,
     spominjanje druge zgrade u opisu se ignoriše)
  3. "A Blok" je strožiji: samo "a blok" kao zaseban token, ne "a blok"
     bilo gde u tekstu (rešava koliziju kad opis kaže "u blizini A bloka")
  4. "Soul" (samo prezime) izbačen iz ključnih reči Soul 64
     (rešava lažne pogotke)
"""
import re

# ── BLACKLIST: nesrodna naselja/blokovi koje nikad ne pratimo ──────────
# Ako se pojavi u naslovu/opisu, oglas ide u neidentifikovano bez obzira
# na ostale ključne reči. Ovo hvata "Ledine", "Blok 62", "Blok 70" itd.
NOT_NB = [
    r"\bledine\b",
    r"\bbežanijska\s*kosa\b",
    r"\bzemun\b",
    r"\bdorćol\b",
    r"\bdedinje\b",
    r"\bvožnjak\b",
    r"\bvoždovac\b",
    r"\bmirijevo\b",
    r"\bpalilula\b",
    r"\bkaraburma\b",
    r"\bvračar\b",
    r"\bkrunska\b",
    r"\bkarađorđeva\b",
    # Susedni blokovi koji nisu naši:
    # A Blok je u Bloku 21, drugi blokovi su druge zgrade
    r"\bblok\s*(2[2-9]|[3-9]\d|1\d\d)\b",  # Blok 22-199
    r"\bbloku?\s*(2[2-9]|[3-9]\d|1\d\d)\b",
]

# Prioritet je bitan — duži/specifičniji match mora biti PRE kraćeg.
# Primer: "West 65 Kula" mora biti pre "West 65", inače kraći match uvek pobedi.
# Svaka zgrada: (display_name, [lista regex obrazaca sa \b granicama])
BUILDINGS = [
    # ── Specifičniji match pre opštijeg ───────────────────────────────
    ("West 65 Kula",   [r"\bwest\s*65\s*kula\b", r"\bwest\s*kula\b",
                         r"\bwest\s*65\s*tower\b", r"\bwest\s*tower\b"]),
    # ── Ostale zgrade po abecedi ──────────────────────────────────────
    # A Blok: TRAŽI reč "a blok" ali ne u kontekstu "A bloka" (padež)
    # koji često se javlja u opisima "u blizini A bloka".
    # Rešenje: hvatamo samo osnovni oblik "a blok" na granicama reči,
    # što isključuje "a bloka", "a bloku", "A blokovima" itd.
    ("A Blok",         [r"\ba\s+blok\s+faza\b",
                         r"\ba[-\s]blok\b(?!\w)",  # "a blok" ne "a bloka"
                         r"\ba\s+blokovi\b"]),
    ("Airport Garden", [r"\bairport\s*garden\b"]),
    ("Bel Mondo",      [r"\bbel\s*mondo\b", r"\bbelmondo\b"]),
    ("Belvil",         [r"\bbelville\b", r"\bbelvil\b"]),
    ("Elixir Garden",  [r"\belixir\s*garden\b", r"\beliksir\s*garden\b"]),
    ("Kennedy Residence", [r"\bkennedy\s*residence(s)?\b"]),
    ("Lastavica",      [r"\blastavic[ae]\b"]),
    ("Lux 51",         [r"\blux\s*51\b"]),
    ("New Minel",      [r"\bnew\s*minel\b", r"\bnovi\s*minel\b"]),
    ("Pupinova palata",[r"\bpupinova\s*palata\b"]),
    ("Sakura Park",    [r"\bsakura\s*park\b"]),
    ("Savada",         [r"\bsavaada\b", r"\bsavada\b"]),
    # Soul 64: samo tačno "Soul 64" ili "Soul64", NIKAD samo "soul"
    # (bila je greška — reč "soul" je preterano labava)
    ("Soul 64",        [r"\bsoul\s*64\b"]),
    ("The One",        [r"\bthe\s*one\b"]),

    # ── West 65 KOMPLEKS ─────────────────────────────────────────────────
    # "West 65" je naziv kompleksa. Pod-zgrade unutar kompleksa
    # (Wellport, Zepterra, West 65 Kula) moraju biti navedene PRE opšteg
    # "West 65" jer naslovi oglasa cesto pominju oba imena zajedno
    # ("West 65 Zeptera Penthouse", "West 65 Wellport 140m2").
    # Argument (Nikola, 10.07.2026): "Ako je oglas stvarno za opšti
    # West 65, niko neće u naslov staviti Zepteru ili Wellport." Dakle
    # spomen pod-zgrade je uvek jaci signal od kompleksa.
    # Redosled: sve pod-zgrade PRE "West 65".
    #
    # BUDUĆE PROŠIRENJE: ako se doda nova pod-zgrada West 65 kompleksa,
    # STAVI JE OVDE (pre West 65), ne dole na kraj liste.
    ("Wellport",       [r"\bwe?ll?port\b"]),  # hvata Wellport, Welport (tipfeler)
    ("Zepterra",       [r"\bzepterr?a\b"]),  # hvata Zepterra, Zeptera
    # (West 65 Kula je vec na vrhu liste — najspecificniji match)
    ("West 65",        [r"\bwest\s*65\b"]),
]

# Nazivi koji se koriste u API responsu / JSON fajlovima
BUILDING_NAMES = [b[0] for b in BUILDINGS]


def _is_blacklisted(text: str) -> bool:
    """True ako tekst spominje nesrodno naselje ili blok koji ne pratimo."""
    for pattern in NOT_NB:
        if re.search(pattern, text, re.I):
            return True
    return False


def _match_in(text: str) -> str | None:
    """Interna funkcija — pretraži tekst po redosledu iz BUILDINGS."""
    for display_name, patterns in BUILDINGS:
        for pat in patterns:
            if re.search(pat, text, re.I):
                return display_name
    return None


def detect_building(text: str, title: str = None, description: str = None) -> str | None:
    """
    Detektuje zgradu iz teksta oglasa.

    Preporučeni način poziva: detect_building(title=t, description=d)
    Naslov ima prioritet nad opisom — ako naslov jasno pogađa zgradu,
    spominjanje druge zgrade u opisu se ignoriše.

    Backward compat: detect_building(text) i dalje radi kao pre, ali
    manji je prioritet naslova pa je slabiji za precizne slučajeve.

    Vraća ime zgrade ili None (ako je blacklisted ili nema pogodka).
    """
    # Blacklist check — svaki tekst (naslov ili opis ili kombinovan)
    combined = " ".join(filter(None, [title, description, text])).strip()
    if not combined:
        return None
    if _is_blacklisted(combined):
        return None

    # Prioritet: prvo naslov (ako je dostupan), pa tek onda opis
    if title:
        title_match = _match_in(title)
        if title_match:
            return title_match

    if description:
        return _match_in(description)

    # Backward compat: ako je poslat samo combined tekst
    return _match_in(text) if text else None
