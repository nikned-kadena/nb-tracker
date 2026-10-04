#!/usr/bin/env python3
"""
agencija_iz_opisa.py — prepoznaje posrednika iz teksta oglasa.

Scraperi za 4zida / Nadji Dom citaju agenciju samo iz JSON-LD (`seller.name`),
a tamo je cesto nema. `agencija = null` NIJE vlasnik: u opisu pise provizija,
"Agencija: X DOO", "Opsti uslovi poslovanja X", sajt agencije i sl.

Dva nezavisna odgovora:
  ima_proviziju(opis) -> True | False | None
        True  = tekst pominje proviziju/naknadu koju placa kupac/zakupac,
                ili broj licence / registar posrednika  -> POSREDNIK
        False = eksplicitno "bez provizije", "direktna prodaja"  -> investitor
        None  = nema signala
  ime_agencije(opis)  -> (prikazno_ime | None, izvor)
        izvor: 'kanon' (prepoznato u tabeli ispod), 'doo' (izvuceno ime, nije
        u tabeli — za pregled), None.

Prikazna imena MORAJU da se poklope sa vrednostima u data/agencije_mapping.json
(da Agencije tab ne dobije dve verzije iste agencije).
"""
import re

_DIJ = str.maketrans({"č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "dj",
                      "Č": "C", "Ć": "C", "Š": "S", "Ž": "Z", "Đ": "Dj"})


def _n(s: str) -> str:
    return (s or "").translate(_DIJ).lower().replace("\xa0", " ").replace("&quot;", '"').replace("&#039;", "'")


# prikazno ime -> regexi nad NORMALIZOVANIM tekstom (bez dijakritika, lowercase)
KANON = {
    "Kuca i Stan":        [r"kuca\s+i\s+stan", r"kucaistan"],
    "Benefit Nekretnine": [r"benefit\s+nekretnine", r"benefitnekretnine"],
    "Maxis Group":        [r"maxis\s+group"],
    "Beocity Nekretnine": [r"beocity", r"beo\s*city\s+nekretnine"],
    "Divis Nekretnine":   [r"divis\s+nekretnine"],
    "Art Nekretnine":     [r"art\s+nekretnine"],
    "BG Posrednik":       [r"bg\s+posrednik"],
    "Artopolis":          [r"artopolis"],
    "Mavikent":           [r"mavikent"],
    "Euro-Winner":        [r"euro-?\s?winner", r"lider\s+nekretnine"],
    "Domigor":            [r"domigor"],
    "Dogma Nekretnine":   [r"dogma\s+nekretnine", r"\bdogma\b\s+beograd"],
    "Etagi":              [r"etagi"],
    "Tukodi":             [r"tukodi"],
    "Porta Nekretnine":   [r"porta\s+nekretnine"],
    "SM Nekretnine":      [r"sm\s+nekretnine"],
    "Keller Williams":    [r"keller\s+williams", r"\bkw\s+cvetkovic"],
    "Smart Pierre":       [r"smartpierre", r"smart\s+pierre"],
    "Prince Nekretnine":  [r"princenekretnine", r"prince\s+nekretnine"],
    "Pactum":             [r"pactum"],
    "Teofil Nekretnine":  [r"teofil\s*nekretnine"],
    "Hill Nekretnine":    [r"hillnekretnine", r"hill\s+nekretnine"],
    "Ikat Nekretnine":    [r"ikatnekretnine", r"ikat\s+nekretnine"],
    "Beostil Nekretnine": [r"beostil"],
    "Oz Nekretnine":      [r"oznekretnine"],
    "Astra Nekretnine":   [r"astranekretnine", r"astranowa"],
    "Domea 88":           [r"domea\s?88"],
    "Jaric Nekretnine":   [r"jaricnekretnine", r"jaric\s+nekretnine"],
    "Gigant":             [r"gigant\.rs", r"gigant\s+nekretnine"],
    "Lav Nekretnine":     [r"\blav\s+nekretnine"],
    "Novi Kvadrati":      [r"novi\s+kvadrati"],
    "Residence Hills":    [r"residence\s+hills"],
}
_KANON_RX = [(ime, re.compile("|".join(p))) for ime, p in KANON.items()]

# Registrovana ime iz mape se dodaje u runtime (ucitaj_mapu): ime se trazi samo
# u kontekstu potpisa (DOO / "Agencija:" / "poslovanja") da "Residence" iz
# naziva zgrade ne bi postao agencija.

_RX_AG = re.compile(r"agencij[ae]\s*[:\-–]\s*([^\n]{3,70})")
_RX_USL = re.compile(r"(?:uslovima?|uslova)\s+poslovanja\s+(?:agencije\s+|posrednika\s+|kompanije\s+)?[\"'“„]*([a-z0-9][^\n,.;\"”]{2,50})")
_RX_DOO = re.compile(r"([a-z0-9][a-z0-9&'\- ]{2,35}?)\s+d\.?\s?o\.?\s?o\.?\b")
_STOP = {"agencija", "agencije", "nekretnine", "posrednik", "posrednika", "i", "stan"}

_RX_PROV = re.compile(
    r"(?:proviz|naknad|nadoknad)\w*[^\n]{0,60}?\d+(?:[.,]\d+)?\s?%"
    r"|\d+(?:[.,]\d+)?\s?%\s*(?:provizij|od\s+(?:kupoprodajne|ugovorene|cene|zakup|dogovorene))"
    r"|proviz\w+\s+(?:se\s+)?(?:naplacuje|placa|je\s+obaveza|snosi|kupac|zakupac)"
    r"|(?:agencijsk|posrednick)\w*\s+(?:proviz|naknad)"
    r"|registr\w*\s+posrednik|broj\s+licence|licenc[ae]\s*(?:br|broj)?\s*\d+"
    r"|opsti\w*\s+uslov\w*\s+poslovanja")
_RX_BEZ = re.compile(
    r"bez\s+(?:agencijske\s+|posredni\w+\s+)?proviz\w*|direktna\s+prodaja|prodaja\s+direktno"
    r"|nema\s+proviz\w*|bez\s+posrednik\w*|direktno\s+od\s+investitora|provizija\s+nije\s+obracunata")


def ima_proviziju(opis):
    t = _n(opis)
    if not t.strip():
        return None
    prov = bool(_RX_PROV.search(t))
    bez = bool(_RX_BEZ.search(t))
    if prov and not bez:
        return True
    if bez and not prov:
        return False
    if prov and bez:
        # "bez provizije za kupca" uz registar posrednika ostaje posredovanje
        # samo ako ima licenca/registar; inace investitor
        return True if re.search(r"registr\w*\s+posrednik|broj\s+licence|licenc", t) else False
    return None


def _ocisti(x: str) -> str:
    x = re.sub(r"\b(d\.?o\.?o\.?|beograd|belgrade|tel.*|e-?mail.*)\b.*$", "", x.strip(), flags=re.I)
    return re.sub(r"[\s,:;\-–]+$", "", x).strip()


def _titlecase(x: str) -> str:
    return " ".join(w.capitalize() if not w.isupper() or len(w) > 3 else w for w in x.split())


def ime_agencije(opis):
    t = _n(opis)
    if not t.strip():
        return None, None
    # Kanonska imena trazimo prvo u repu teksta (potpis), pa u celom
    rep = t[-600:]
    for ime, rx in _KANON_RX:
        if rx.search(rep):
            return ime, "kanon"
    for ime, rx in _KANON_RX:
        if rx.search(t):
            return ime, "kanon"
    # Opste izvlacenje: kandidat ide na pregled, ne u tabelu
    for rx in (_RX_AG, _RX_USL, _RX_DOO):
        for m in rx.finditer(t):
            c = _ocisti(m.group(1))
            if len(c) >= 4 and c not in _STOP and not c.isdigit() and not re.search(r"\d{3,}", c):
                return _titlecase(c), "doo"
    return None, None


def odredi(opis, agencija_postojeca=None):
    """-> (agencija, agencija_izvor, posrednik)  posrednik: True/False/None"""
    prov = ima_proviziju(opis)
    if agencija_postojeca:
        return agencija_postojeca, "scraper", True
    ime, izv = ime_agencije(opis)
    if ime and prov is not False:
        return ime, "opis_" + izv, True
    if prov is True:
        return None, None, True          # posrednik, ime nepoznato
    if prov is False:
        return None, None, False         # investitor / vlasnik
    return None, None, None              # nepoznato
