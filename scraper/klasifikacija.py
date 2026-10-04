#!/usr/bin/env python3
"""
klasifikacija.py — ispravke oznake zgrade i tipa prodaje u PROJEKCIJI.

ZASTO POSTOJI (04.10.2026)
--------------------------
Registar cuva oznaku zgrade onakvu kakvu je klasifikator dao u trenutku kad je
oglas prvi put viden. Pravila klasifikatora su se posle toga menjala (npr.
08-09.07.2026: ulica bez kucnog broja vise ne vodi na St. Regis), ali registar
nikad nije ponovo klasifikovan. Rezultat na preseku od 02.10.2026:
  - 13 od 736 oglasa (BnV): naslov imenuje jednu zgradu, a oznaka je druga
    ("Bw Kings Park 3.0" vodjen kao St. Regis, "BW Aria" kao Iris, ...);
  - 8 St. Regis oglasa ciji naslov navodi samo Savska/Hercegovacka/Luke
    Celovica i cije cene po m2 nemaju veze sa St. Regis-om;
  - 5 oglasa sa zaostalom oznakom "BW (Hercegovacka)";
  - 3 od 273 oglasa (NB): "Soul 64" naslov u A Bloku, "Sakura Park" u Belvilu.

Ovaj modul NE dira registar. Primenjuje se samo pri projekciji (project.py),
pa je ispravka retroaktivna, ponovljiva i bezbedna za povlacenje.

PRAVILA (po prioritetu)
-----------------------
1. Zaostale oznake tipa "BW (Hercegovacka)" -> "BW (neidentifikovano)".
2. Ako NASLOV imenuje zgradu, naslov pobedjuje sacuvanu oznaku.
   Izuzetak (NB): sacuvano "West 65 Kula", naslov "u kuli West 65" -> ostaje Kula.
3. Ako naslov ne imenuje zgradu, a navodi samo ulicu koja ne odgovara St. Regis-u
   (Hercegovacka, Luke Celovica, ili Savska bez broja 1/3), a sacuvano je
   "BW St. Regis" -> neidentifikovano.
4. (04.10.2026, v2) Ako je oznaka i dalje "neidentifikovano", a opis oglasa
   (keš 4zida/Nadji Dom) po strogim pravilima modula zgrada_iz_opisa.py
   imenuje zgradu — uzima se ta zgrada (izvor `opis`, `zgrada_orig` cuva staro).
   Halo opisi se ne cuvaju, pa se za Halo oglase ovaj korak preskace.
5. Inace ostaje sacuvana oznaka (potekla iz opisa/adrese oglasa, koje ovde
   nemamo). Polje `zgrada_izvor` kaze koliko je oznaka proverljiva:
       naslov  - naslov imenuje tu zgradu (pouzdano)
       ulica   - naslov navodi samo ulicu, oznaka potice iz opisa (neproveren)
       opis    - naslov nema ni ime ni ulicu, oznaka potice iz opisa (neproveren)
       ispravljeno - oznaka je promenjena ovim modulom (vidi `zgrada_orig`)
       opis_agenta - zgrada procitana iz opisa agenta (4zida/Nadji Dom), vidi `zgrada_orig`

OGLASI KOJI NISU BW (v2)
------------------------
`van_bw(e)` — naslov ili ulica odgovara NOT_BW listi iz buildings.py (npr. Skyline
Belgrade/Kneza Milosa, Kraljevica Marka, Bul. kralja Aleksandra). Takvi zapisi se
izostavljaju iz projekcije (u registru ostaju), isto kao sto ih prijem odbacuje.
Proverava se SAMO naslov i ulica, ne ceo opis (opis moze da pominje okolinu).

TIP PRODAJE (samo BnV, samo prodaja)
------------------------------------
Investitor oglasava cene koje se zavrsavaju na 888 EUR (x.xxx.888). To je
"direktna prodaja"; ostalo je "resale". Isto pravilo koristi dashboard
(isDirektna: cena % 1000 === 888) — ovde je zapisano u podatke da izvestaji i
dashboard imaju JEDNU definiciju.

SUMNJIVA CENA PO m2
-------------------
Za zgrade sa >= 5 aktivnih oglasa, oglas ciji je EUR/m2 van opsega
0,6x-1,7x medijane zgrade dobija `cena_m2_sumnjiva: true`. Oglas se NE uklanja —
samo se oznaci, da izvestaj i dashboard mogu da ga izdvoje.
"""

import re
import statistics

try:
    import buildings as _b
except Exception:                                    # pragmaticno: bez buildings.py
    _b = None

try:
    from zgrada_iz_opisa import zgrada_iz_opisa as _iz_opisa   # samo BnV
except Exception:
    _iz_opisa = None

NEIDENT = "BW (neidentifikovano)"
_OPISI = {}          # url -> tekst opisa (iz cache_*_{mode}.json), puni ucitaj_opise()
# Direktna prodaja postoji samo u BnV (BnV buildings.py ima ALL_BUILDINGS).
TIP_PRODAJE_AKTIVAN = bool(_b is not None and hasattr(_b, "ALL_BUILDINGS"))
DONJA, GORNJA, MIN_UZORAK = 0.6, 1.7, 5
ULICE_NIJE_ST_REGIS = ("hercegovačka", "luke ćelovića")


def iz_naslova(naslov, sprat=None):
    """Zgrada koju naslov IMENUJE, ili None."""
    if _b is None or not naslov:
        return None
    try:
        if hasattr(_b, "_find_by_direct_name"):       # BnV klasifikator
            t = naslov.lower().replace("’", "'")
            return _b._find_by_direct_name(t) or _b._find_by_alias(t, sprat)
        if hasattr(_b, "_match_in"):                  # NB klasifikator
            return _b._match_in(naslov)
    except Exception:
        return None
    return None


def ucitaj_opise(data_dir, mode):
    """Napuni url->opis iz kesa scrapera (4zida, Nadji Dom). Halo nema opis."""
    global _OPISI
    import json
    from pathlib import Path
    _OPISI = {}
    for f in sorted(Path(data_dir).glob(f"cache_*_{mode}.json")):
        try:
            for url, v in json.loads(f.read_text(encoding="utf-8")).items():
                if isinstance(v, dict) and v.get("opis"):
                    _OPISI[url] = v["opis"]
        except Exception:
            continue
    return len(_OPISI)


def _opis_za(e):
    for u in (e.get("source_urls") or []):
        if u in _OPISI:
            return _OPISI[u]
    return None


try:
    from agencija_iz_opisa import odredi as _ag_odredi
except Exception:                                   # bez modula: ponasanje kao pre
    _ag_odredi = None


def agencija_za(e):
    """-> (agencija, agencija_izvor, posrednik). Scraperova agencija ima prednost;
    inace se trazi u opisu. posrednik: True / False (investitor-vlasnik) / None."""
    ag = e.get("agencija")
    if _ag_odredi is None:
        return ag, ("scraper" if ag else None), (True if ag else None)
    return _ag_odredi(_opis_za(e), ag)


def van_bw(e):
    """True ako naslov/ulica oglasa odgovara NOT_BW listi (oglas nije u BW)."""
    nb = getattr(_b, "NOT_BW", None) if _b else None
    if not nb:
        return False
    tekst = ((e.get("naslov") or "") + " " + (e.get("ulica") or "")).lower()
    return any(re.search(p, tekst, re.I) for p in nb)


_SAVSKA = re.compile(r"\bsavska\b")
_SAVSKA_1_3 = re.compile(r"\bsavska(?:\s+ulica)?\s+[13](?!\d|[.,]\d)")


def _savska_bez_broja(t):
    """Savska bez kucnog broja 1 ili 3 (St. Regis) — isto pravilo kao ADDRESS_MAP
    u buildings.py: ulica bez broja ne dokazuje St. Regis."""
    return bool(_SAVSKA.search(t)) and not _SAVSKA_1_3.search(t)


def _ulice_u_naslovu(naslov):
    t = (naslov or "").lower()
    ulice = list(getattr(_b, "STREET_FALLBACK", {}).keys()) if _b else []
    return [u for u in ulice if u in t]


def ispravi_zgradu(e):
    """(zgrada, izvor, orig) za zapis iz registra. orig je None ako nije menjano.

    Prvo pravila 1-3 (naslov), pa pravilo 4: opis agenta za oglase koji su i
    dalje neidentifikovani. Izvor `opis_agenta` = zgrada procitana iz opisa."""
    zgrada, izvor, orig = _ispravi_po_naslovu(e)
    opis = _opis_za(e) if _iz_opisa is not None else None

    def _strogo():
        try:
            z = _iz_opisa(opis, e.get("sprat"))
        except Exception:
            return None
        return z if z and z != NEIDENT else None

    if zgrada == NEIDENT and opis:
        z = _strogo()
        if z:
            return z, "opis_agenta", e.get("zgrada")
        return zgrada, izvor, orig

    # PRAVILO "ULICA NE ODREDJUJE ZGRADU, OZNAKA BEZ DOKAZA NE VAZI" (04.10.2026)
    # Zgrada se prihvata samo iz (1) naslova koji je imenuje ili (2) opisa
    # agenta (strogo pravilo). Sacuvana oznaka iz registra koja nema takav
    # dokaz poticala je iz ulice ("Bulevar Vudroa Vilsona" -> Iris/Hudson/
    # Sava...), a to je pogadjanje: u 47 slucajeva opis imenuje DRUGU zgradu
    # (BW Luna vodjena kao St. Regis), u dodatnih ~20 ne imenuje nijednu.
    # Izuzetak: Halo oznaka (Halo scraper cita pun opis) kad ulica nije u
    # naslovu — dok Halo scraper ne cuva opis, ne moze se proveriti.
    if _iz_opisa is not None and zgrada not in (None, NEIDENT) and izvor in ("opis", "ulica"):
        halo = "halo" in (e.get("sources") or [])
        ulica_u_naslovu = izvor == "ulica" or bool(_ulice_u_naslovu(e.get("ulica") or ""))
        if opis:
            z = _strogo()
            if z == zgrada:
                return zgrada, "opis_agenta", orig
            if z:
                return z, "opis_agenta", e.get("zgrada")
            if not halo or ulica_u_naslovu:
                return NEIDENT, "bez_dokaza", e.get("zgrada")
        elif not halo or ulica_u_naslovu:
            return NEIDENT, "bez_dokaza", e.get("zgrada")
    return zgrada, izvor, orig


def _ispravi_po_naslovu(e):
    sacuvana = e.get("zgrada")
    naslov = e.get("naslov") or ""
    zgrada = sacuvana

    # 1. zaostale oznake po ulici
    if isinstance(zgrada, str) and zgrada.startswith("BW (") and zgrada != NEIDENT:
        zgrada = NEIDENT

    # 2. naslov imenuje zgradu
    imenovana = iz_naslova(naslov, e.get("sprat"))
    if imenovana:
        kula_izuzetak = (sacuvana == "West 65 Kula" and imenovana == "West 65")
        # sacuvana oznaka je preciznija varijanta imenovane (npr. "BW Sava Riverline"
        # naspram "BW Sava") — to je doterivanje, ne protivrecnost; ostaje sacuvana.
        preciznija = isinstance(zgrada, str) and zgrada != imenovana and zgrada.startswith(imenovana)
        if preciznija:
            return zgrada, "naslov", None
        if imenovana != zgrada and not kula_izuzetak:
            return imenovana, "ispravljeno", sacuvana
        if not kula_izuzetak:
            return (zgrada, "naslov", None) if zgrada == sacuvana else (zgrada, "ispravljeno", sacuvana)

    # 3. ulica koja ne odgovara St. Regis-u
    t = naslov.lower()
    if zgrada == "BW St. Regis" and not imenovana and (
            any(u in t for u in ULICE_NIJE_ST_REGIS) or _savska_bez_broja(t)):
        return NEIDENT, "ispravljeno", sacuvana

    if zgrada != sacuvana:
        return zgrada, "ispravljeno", sacuvana
    # 4. ostaje sacuvana oznaka
    izvor = "ulica" if _ulice_u_naslovu(naslov) else "opis"
    return zgrada, izvor, None


def tip_prodaje(cena, mode):
    if not TIP_PRODAJE_AKTIVAN or mode != "prodaja" or cena is None:
        return None
    return "direktna" if cena % 1000 == 888 else "resale"


def oznaci_sumnjive(listings):
    """Dodaje `cena_m2_sumnjiva` svakom oglasu. Vraca broj oznacenih."""
    po_zgradi = {}
    for l in listings:
        if l.get("cena") and l.get("m2"):
            po_zgradi.setdefault(l.get("zgrada"), []).append(l["cena"] / l["m2"])
    medijane = {z: statistics.median(v) for z, v in po_zgradi.items() if len(v) >= MIN_UZORAK}
    n = 0
    for l in listings:
        m = medijane.get(l.get("zgrada"))
        sumnjiva = False
        if m and l.get("cena") and l.get("m2"):
            r = (l["cena"] / l["m2"]) / m
            sumnjiva = not (DONJA <= r <= GORNJA)
        l["cena_m2_sumnjiva"] = sumnjiva
        n += sumnjiva
    return n
