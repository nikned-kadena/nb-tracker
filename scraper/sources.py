#!/usr/bin/env python3
"""
sources.py — scraperi za 4zida i Nadji Dom.

ZASTO SU LAKSI OD HALO-A
------------------------
Oba portala serviraju gotov HTML sa `schema.org` JSON-LD blokom na svakoj
detaljnoj stranici. Umesto da pogadjamo CSS klase (koje se menjaju svaki put
kad portal promeni dizajn), citamo strukturirani podatak koji je tu zato da
bi ga Google citao. To je neuporedivo stabilnije od parsiranja kartica.

Ni jedan ni drugi nemaju anti-bot vendor (provereno 30.09.2026: nema
DataDome, PerimeterX ni Cloudflare challenge), pa NE trebaju ScraperAPI
krediti — idu direktnim `requests` pozivom. Zato je USE_SCRAPERAPI podesiv:
ako portal jednog dana uvede zastitu, prebaci se na True i kod radi dalje.

DVA KORAKA, ISTA LOGIKA KAO NB
------------------------------
  Korak 1: sa listing stranica skupi URL-ove oglasa (jeftino)
  Korak 2: za oglase koje NEMAMO u kesu povuci detaljnu stranicu i procitaj
           JSON-LD (skupo, ali samo za nove)

Kes je isti mehanizam kao u NB scraper-u i zivi u data/cache_{source}_{mode}.json.

BONUS: OBA PORTALA DAJU KOORDINATE
----------------------------------
`geo.latitude` / `geo.longitude` stoje u JSON-LD-u. To znaci da za ove dve
izvora geokodiranje ne treba uopste — koordinata dolazi besplatno. Halo je
ne daje, pa nam ovi oglasi sluze i kao referentni skup: kad isti stan
vidimo i na Halo-u i na 4zida, koordinata sa 4zida se prenosi na spojeni
zapis kroz store.py.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent.parent / "data"
CACHE_TTL_DAYS = 30
PAGE_DELAY = 2.0
DETAIL_DELAY = 1.0
MAX_PAGES = 40

USE_SCRAPERAPI = False  # prebaci na True ako portal uvede anti-bot
SCRAPER_API_KEY = ""

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

# ── rute ────────────────────────────────────────────────────────────────
# SVE CETIRI 4zida rute i SVE CETIRI nadjidom rute su provere 30.09.2026
# otvaranjem u browseru — nisu pogodjene po sablonu.
#
# 4zida slug je {mikrolokacija}-{opstina}-{grad} ili {opstina}-{grad}.
# PAZNJA: oblik "/prodaja-stanova/beograd/novi-beograd" IZGLEDA ispravno
# ali tiho pada nazad na ceo Beograd (naslov ostane "Prodaja stanova
# Beograd" i vracaju se oglasi iz Zemuna). Ispravno je "novi-beograd-beograd".
#
# Nadji Dom vraca celu opstinu; BnV se izdvaja filterom po URL-u oglasa,
# jer detaljni URL sadrzi mikrolokaciju ("...-Beograd+na+vodi-...").
ROUTES = {
    "4zida": {
        "bnv": {
            "prodaja": "https://www.4zida.rs/prodaja-stanova/beograd-na-vodi-savski-venac-beograd",
            "renta":   "https://www.4zida.rs/izdavanje-stanova/beograd-na-vodi-savski-venac-beograd",
        },
        "nb": {
            "prodaja": "https://www.4zida.rs/prodaja-stanova/novi-beograd-beograd",
            "renta":   "https://www.4zida.rs/izdavanje-stanova/novi-beograd-beograd",
        },
    },
    "nadjidom": {
        "bnv": {
            "prodaja": "https://www.nadjidom.com/sr/nekretnine/prodaja/stanovi+Beograd+Savski+venac",
            "renta":   "https://www.nadjidom.com/sr/nekretnine/izdavanje/stanovi+Beograd+Savski+venac",
        },
        "nb": {
            "prodaja": "https://www.nadjidom.com/sr/nekretnine/prodaja/stanovi+Beograd+Novi+Beograd",
            "renta":   "https://www.nadjidom.com/sr/nekretnine/izdavanje/stanovi+Beograd+Novi+Beograd",
        },
    },
}

# Provera pri pokretanju: ako 4zida tiho vrati ceo Beograd, prekini umesto
# da upises 9.000 oglasa iz cele varosi u BnV ili NB registar.
OCEKIVANI_H1 = {
    ("4zida", "bnv"): "beograd na vodi",
    ("4zida", "nb"): "novi beograd",
}

# Nadji Dom vraca celu opstinu; BnV se prepoznaje po URL-u oglasa.
NADJIDOM_BNV_FILTER = "Beograd+na+vodi"

STRUCTURE_MAP = {
    "1.0": "Garsonjera/Studio", "1.5": "Jednoiposoban",
    "2.0": "Dvosoban", "2.5": "Dvoiposoban", "3.0": "Trosoban",
    "3.5": "Troiposoban", "4.0": "Četvorosoban", "4.5": "Četvoriposoban",
    "5.0": "Petosoban+",
}

SLUG_SOBE = {
    "garsonjera": 1.0, "jednosoban": 1.0, "jednoiposoban": 1.5,
    "dvosoban": 2.0, "dvoiposoban": 2.5, "trosoban": 3.0,
    "troiposoban": 3.5, "cetvorosoban": 4.0, "cetvoroiposoban": 4.5,
    "petosoban": 5.0,
}


# ── mreza ───────────────────────────────────────────────────────────────

def fetch(url: str, tries: int = 3):
    for i in range(tries):
        try:
            if USE_SCRAPERAPI and SCRAPER_API_KEY:
                r = requests.get("https://api.scraperapi.com", timeout=90, params={
                    "api_key": SCRAPER_API_KEY, "url": url, "render": "false"})
            else:
                r = requests.get(url, timeout=45, headers={
                    "User-Agent": UA,
                    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
                })
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429):
                print(f"  ⚠ {r.status_code} na {url[:70]} — cekam {(i+1)*10}s", file=sys.stderr)
                time.sleep((i + 1) * 10)
                continue
            return None
        except Exception as e:
            msg = str(e)
            if SCRAPER_API_KEY:
                msg = msg.replace(SCRAPER_API_KEY, "***")
            print(f"  ⚠ Greska ({i+1}/{tries}) {url[:60]}: {msg}", file=sys.stderr)
            time.sleep(3)
    return None


# ── JSON-LD ─────────────────────────────────────────────────────────────

def json_ld_blocks(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            d = json.loads(s.string or s.get_text() or "")
        except Exception:
            continue
        out.extend(d if isinstance(d, list) else [d])
        if isinstance(d, dict) and "@graph" in d:
            out.extend(d["@graph"])
    return [o for o in out if isinstance(o, dict)]


def _ld_type(blocks, *types):
    for b in blocks:
        if b.get("@type") in types:
            return b
    return None


def _num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"([\d]+[.,]?[\d]*)", str(x).replace(".", "").replace(",", "."))
    return float(m.group(1)) if m else None


def _sobe_iz_url(url: str):
    for slug, v in SLUG_SOBE.items():
        if slug in url.lower():
            return v
    return None


def parse_detail(html: str, url: str, mode: str, source: str):
    """Vrati zapis u ISTOM obliku koji pravi Halo scraper."""
    blocks = json_ld_blocks(html)
    if not blocks:
        return None

    listing = _ld_type(blocks, "RealEstateListing")
    apart = _ld_type(blocks, "Apartment", "SingleFamilyResidence", "Residence")
    offer = _ld_type(blocks, "Offer")
    core = apart or listing or {}

    if not core and not offer:
        return None

    # cena
    cena = None
    if offer:
        cena = _num(offer.get("price"))
    if cena is None and listing:
        o = listing.get("offers") or {}
        if isinstance(o, dict):
            cena = _num(o.get("price"))
    if cena is None:
        m = re.search(r"([\d\.]{3,})\s*€", core.get("name", "") or "")
        if m:
            cena = _num(m.group(1))

    # kvadratura
    m2 = None
    area = core.get("area") or core.get("floorSize") or (listing or {}).get("floorSize")
    if isinstance(area, dict):
        m2 = _num(area.get("value"))
    elif area is not None:
        m2 = _num(area)
    if m2 is None:
        m = re.search(r"([\d]+[.,]?[\d]*)\s*m[²2]", core.get("name", "") or "")
        if m:
            m2 = _num(m.group(1))

    # sobe
    sobe = _num(core.get("numberOfRooms")) or _num((listing or {}).get("numberOfRooms"))
    if sobe is None:
        sobe = _sobe_iz_url(url)
    if sobe == 0.5:
        sobe = 1.0

    # adresa, koordinate, sprat
    addr = core.get("address") or (listing or {}).get("address") or {}
    ulica = addr.get("streetAddress") if isinstance(addr, dict) else None
    geo = core.get("geo") or (listing or {}).get("geo") or {}
    lat = _num(geo.get("latitude")) if isinstance(geo, dict) else None
    lon = _num(geo.get("longitude")) if isinstance(geo, dict) else None
    sprat = (listing or {}).get("floorLevel") or core.get("floorLevel")

    naslov = (core.get("name") or (listing or {}).get("name") or "")[:160]
    opis = (core.get("description") or (listing or {}).get("description") or "")[:400]

    ext_id = url.rstrip("/").split("/")[-1]
    if source == "nadjidom":
        m = re.search(r"/details/(\d+)/", url)
        if m:
            ext_id = m.group(1)
    ext_id = ext_id.replace(".html", "")

    seller = core.get("seller") or (listing or {}).get("seller") or {}
    agencija = seller.get("name") if isinstance(seller, dict) else None
    if not agencija:
        brand = (listing or {}).get("brand") or {}
        agencija = brand.get("name") if isinstance(brand, dict) else None

    str_key = str(sobe) if sobe is not None else None
    cena_m2 = round(cena / m2) if (cena and m2) else None

    return {
        "id": f"{source}:{ext_id}",
        "url": url,
        "naslov": naslov,
        "zgrada": None,                     # popunjava buildings.py
        "agencija": agencija,
        "struktura": str_key,
        "str_label": STRUCTURE_MAP.get(str_key, "nepoznato") if str_key else "nepoznato",
        "m2": m2,
        "cena": int(cena) if cena else None,
        "cena_m2": cena_m2,
        "sprat": str(sprat)[:8] if sprat else None,
        "ulica": ulica,
        "lat": lat,
        "lon": lon,
        "opis": opis,
        "mode": mode,
        "source": source,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


# ── korak 1: URL-ovi ────────────────────────────────────────────────────

def collect_urls(source: str, tracker: str, mode: str, max_pages: int = MAX_PAGES):
    base = ROUTES[source][tracker][mode]
    urls, seen, prazne = [], set(), 0

    for page in range(1, max_pages + 1):
        u = base if page == 1 else (
            f"{base}?page={page}" if source == "nadjidom" else f"{base}?strana={page}")
        print(f"  [{source}] listing str. {page}", flush=True)
        html = fetch(u)
        if not html:
            prazne += 1
            if prazne >= 2:
                break
            continue

        soup = BeautifulSoup(html, "lxml")

        # ── zastita: da li smo stvarno na trazenoj lokaciji ────────────
        # 4zida na pogresan slug ne vrati 404 nego TIHO servira ceo Beograd.
        # Bez ove provere bi u BnV registar uletelo 9.000 oglasa iz Zemuna.
        ocek = OCEKIVANI_H1.get((source, tracker))
        if ocek and page == 1:
            h1 = soup.find("h1")
            h1t = (h1.get_text(strip=True) if h1 else "").lower()
            if ocek not in h1t:
                print(f"  ✖ STOP [{source}/{tracker}]: ocekivao '{ocek}' u naslovu, "
                      f"dobio '{h1t[:60]}'. Ruta je verovatno promenjena — "
                      f"prekidam da ne upisem tudje oglase.", file=sys.stderr)
                return []

        nadjeno = 0
        for a in soup.find_all("a", href=True):
            h = a["href"]
            if source == "4zida":
                if not re.search(r"-stan(ova)?/[0-9a-f]{24}$", h) and \
                   not re.search(r"/[0-9a-f]{24}$", h):
                    continue
                if "-stan/" not in h:
                    continue
                full = h if h.startswith("http") else "https://www.4zida.rs" + h
            else:
                if "/details/" not in h:
                    continue
                full = h if h.startswith("http") else "https://www.nadjidom.com" + h
                if tracker == "bnv" and NADJIDOM_BNV_FILTER not in full:
                    continue
            if full not in seen:
                seen.add(full)
                urls.append(full)
                nadjeno += 1

        print(f"      +{nadjeno} (ukupno {len(urls)})")
        if nadjeno == 0:
            prazne += 1
            if prazne >= 2:
                print("      → dve prazne stranice, zaustavljam.")
                break
        else:
            prazne = 0
        time.sleep(PAGE_DELAY)

    return urls


# ── kes ─────────────────────────────────────────────────────────────────

def load_cache(source: str, mode: str) -> dict:
    f = DATA_DIR / f"cache_{source}_{mode}.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_cache(source: str, mode: str, cache: dict) -> int:
    danas = datetime.now(timezone.utc).date()
    ziv = {}
    for k, v in cache.items():
        try:
            d = datetime.fromisoformat(v.get("scraped_at", "")[:10]).date()
        except Exception:
            d = danas
        if (danas - d).days <= CACHE_TTL_DAYS:
            ziv[k] = v
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / f"cache_{source}_{mode}.json").write_text(
        json.dumps(ziv, ensure_ascii=False), encoding="utf-8")
    return len(cache) - len(ziv)


# ── glavni ulaz ─────────────────────────────────────────────────────────

def scrape(source: str, tracker: str, mode: str, full_refresh: bool = False,
           max_pages: int = MAX_PAGES):
    print(f"\n=== {source.upper()} [{tracker}] [{mode}] "
          f"{'FULL' if full_refresh else 'inkrementalno'} ===")

    urls = collect_urls(source, tracker, mode, max_pages)
    if not urls:
        print(f"  ⚠ {source}: nijedan URL — preskacem.", file=sys.stderr)
        return []

    cache = {} if full_refresh else load_cache(source, mode)
    out, novi = [], 0

    for i, u in enumerate(urls, 1):
        if u in cache:
            out.append(cache[u])
            continue
        html = fetch(u)
        if not html:
            continue
        rec = parse_detail(html, u, mode, source)
        if rec:
            cache[u] = rec
            out.append(rec)
            novi += 1
        if i % 25 == 0:
            print(f"      detalji {i}/{len(urls)} (novih {novi})", flush=True)
        time.sleep(DETAIL_DELAY)

    ociscen = save_cache(source, mode, cache)
    print(f"  [{source}] URL-ova {len(urls)} | iz kesa {len(out)-novi} | "
          f"novih {novi}" + (f" | ocisceno {ociscen}" if ociscen else ""))
    return out


def klasifikuj(listings: list, scraper_dir: Path):
    """Propusti kroz buildings.py istog repo-a (BnV v6 / NB v4)."""
    sys.path.insert(0, str(scraper_dir))
    try:
        from buildings import canonical_building, is_blacklisted
    except Exception as e:
        print(f"  ⚠ buildings.py nedostupan ({e}) — zgrada ostaje prazna.", file=sys.stderr)
        return listings

    out = []
    for l in listings:
        ctx = f"{l.get('naslov','')} {l.get('ulica','') or ''} {l.get('opis','')}"
        ulica = l.get("ulica") or ""
        try:
            if is_blacklisted(l.get("naslov", ""), ctx, ulica):
                continue
            l["zgrada"] = canonical_building(l.get("naslov", ""), ctx, ulica, l.get("sprat"))
        except Exception as e:
            print(f"  ⚠ klasifikacija pala za {l.get('id')}: {e}", file=sys.stderr)
            l["zgrada"] = None
        out.append(l)
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["4zida", "nadjidom"], required=True)
    ap.add_argument("--tracker", choices=["bnv", "nb"], required=True)
    ap.add_argument("--mode", choices=["prodaja", "renta"], required=True)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--max-pages", type=int, default=MAX_PAGES)
    a = ap.parse_args()

    recs = scrape(a.source, a.tracker, a.mode, a.full, a.max_pages)
    recs = klasifikuj(recs, Path(__file__).parent)

    sys.path.insert(0, str(Path(__file__).parent))
    import store, dom_stats
    store.update(DATA_DIR, a.mode, recs, source=a.source)
    dom_stats.build(DATA_DIR, a.mode)
