"""
NB Tracker — Halo Oglasi scraper za Novi Beograd
Koristi ScraperAPI (render=false) za bypass Cloudflare.
Scrape-uje sve strane, filtrira po zgradama iz buildings.py.

Pokretanje:
  python scrape_halo.py --mode prodaja
  python scrape_halo.py --mode renta

Env var:
  SCRAPER_API_KEY  — ScraperAPI ključ
"""

import os
import sys
import json
import re
import argparse
import hashlib
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Putanje ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from buildings import detect_building, BUILDING_NAMES

# ── Konstante ───────────────────────────────────────────────────────────────
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")
SCRAPER_URL = "http://api.scraperapi.com"

BASE_URLS = {
    "prodaja": "https://www.halooglasi.com/nekretnine/prodaja-stanova/beograd-novi-beograd",
    "renta":   "https://www.halooglasi.com/nekretnine/izdavanje-stanova/beograd-novi-beograd",
}

STRUKTURA_MAP = {
    # Tekstualni nazivi
    "garsonjera":      "garsonjera",
    "jednosoban":      "1.0",
    "jednoiposoban":   "1.5",
    "dvosoban":        "2.0",
    "dvoiposoban":     "2.5",
    "trosoban":        "3.0",
    "troiposoban":     "3.5",
    "četvorosoban":    "4.0",
    "četvoroiposoban": "4.5",
    "petosoban":       "5.0",
    "višesoban":       "5.0",
}


# ── Helpers ─────────────────────────────────────────────────────────────────
def scraper_get(url: str) -> requests.Response:
    params = {
        "api_key": SCRAPER_API_KEY,
        "url": url,
        "render": "false",
    }
    resp = requests.get(SCRAPER_URL, params=params, timeout=60)
    resp.raise_for_status()
    return resp


def normalize_id(slug: str) -> str:
    """Stabilan ID od URL slug-a oglasa."""
    return hashlib.md5(slug.encode()).hexdigest()[:12]


def parse_price(text: str) -> float | None:
    text = text.replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", "")
    m = re.search(r"(\d+)", text)
    return float(m.group(1)) if m else None


def parse_m2(text: str) -> float | None:
    m = re.search(r"([\d,\.]+)\s*m", text.lower())
    if m:
        return float(m.group(1).replace(",", "."))
    return None





def parse_struktura(title: str) -> str:
    """Detektuje strukturu iz naslova.
    Podrzava tekstualni format ('Trosoban') i numericki ('3.0', '2,0').
    """
    t = title.lower()
    txt_map = [
        ("garsonjera", "garsonjera"), ("jednoiposoban", "1.5"), ("jednosoban", "1.0"),
        ("dvoiposoban", "2.5"), ("dvosoban", "2.0"),
        ("troiposoban", "3.5"), ("trosoban", "3.0"),
        ("cetvoroiposoban", "4.5"), ("cetvorosoban", "4.0"),
        ("petosoban", "5.0"), ("visesoban", "5.0"),
    ]
    for key, val in txt_map:
        if key in t:
            return val
    # Numericki format: "2.0", "3,0", "4.0" u naslovu
    num_map = {
        "0.5": "garsonjera", "1.0": "1.0", "1.5": "1.5",
        "2.0": "2.0", "2.5": "2.5", "3.0": "3.0", "3.5": "3.5",
        "4.0": "4.0", "4.5": "4.5", "5.0": "5.0",
    }
    m = re.search(r"\b(\d+[.,]\d)\b", t)
    if m:
        num = m.group(1).replace(",", ".")
        if num in num_map:
            return num_map[num]
    return "ostalo"


def scrape_page(url: str) -> tuple[list[dict], bool]:
    """Scrape jedne stranice. Vraća (oglasi, ima_sledece_stranice)."""
    resp = scraper_get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    listings = []
    cards = soup.select("li.product-item")
    if not cards:
        # fallback: stariji selektor
        cards = soup.select(".product-item")

    for card in cards:
        # preskoci banner/premium-only kartice bez linka
        link_tag = card.select_one("a[href*='/nekretnine/']")
        if not link_tag:
            continue

        href = link_tag.get("href", "")
        full_url = f"https://www.halooglasi.com{href}" if href.startswith("/") else href
        slug = href.strip("/").split("/")[-1]
        listing_id = normalize_id(slug)

        title_tag = card.select_one("h3.product-title") or card.select_one(".product-title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        desc_tag = card.select_one(".product-description") or card.select_one(".short-description")
        desc = desc_tag.get_text(strip=True) if desc_tag else ""

        combined = f"{title} {desc}"
        zgrada = detect_building(combined)
        if not zgrada:
            continue  # ne zanima nas

        # Cena
        price_tag = card.select_one(".price-box") or card.select_one("[class*='price']")
        price_text = price_tag.get_text(strip=True) if price_tag else ""
        cena = parse_price(price_text)

        # m²
        m2 = None
        features = card.select("ul.product-features li") or card.select(".product-features li")
        for feat in features:
            legend = feat.select_one("span.legend")
            val_tag = feat.select_one("div.value-wrapper") or feat.select_one(".value")
            if legend and val_tag:
                if "m" in legend.get_text().lower() or "kvadrat" in legend.get_text().lower():
                    m2 = parse_m2(val_tag.get_text())
                    break
        if m2 is None:
            m2 = parse_m2(title) or parse_m2(desc)

        cena_m2 = round(cena / m2) if cena and m2 else None
        struktura = parse_struktura(title)

        # Agencija
        agency_tag = card.select_one(".username") or card.select_one("[class*='user']")
        agencija = agency_tag.get_text(strip=True) if agency_tag else None

        listings.append({
            "id":        listing_id,
            "slug":      slug,
            "url":       full_url,
            "naslov":    title,
            "opis":      desc[:1000],
            "zgrada":    zgrada,
            "struktura": struktura,
            "cena":      cena,
            "m2":        m2,
            "cena_m2":   cena_m2,
            "agencija":  agencija,
            "izvor":     "halo",
        })

    # Paginacija: postoji li sledeća stranica?
    next_btn = soup.select_one("a.next") or soup.select_one("[rel='next']")
    has_next = next_btn is not None

    return listings, has_next


def scrape_all(mode: str) -> list[dict]:
    base = BASE_URLS[mode]
    all_listings = []
    page = 1

    while True:
        url = base if page == 1 else f"{base}?page={page}"
        print(f"  Halo [{mode}] stranica {page} …", flush=True)
        try:
            listings, has_next = scrape_page(url)
        except Exception as e:
            print(f"  GREŠKA na stranici {page}: {e}")
            break

        all_listings.extend(listings)
        print(f"    → {len(listings)} relevantnih oglasa")

        if not has_next or len(listings) == 0:
            break
        page += 1

    return all_listings


# ── Dedup + diff ────────────────────────────────────────────────────────────
def compute_dedup(listings: list[dict]) -> list[dict]:
    """Ukloni duplikate: isti (zgrada, m2, cena) = duplikat."""
    seen = set()
    unique = []
    for l in listings:
        key = (l["zgrada"], l["m2"], l["cena"])
        if key not in seen:
            seen.add(key)
            unique.append(l)
    return unique


def update_history(mode: str, raw: list, unique: list, prev_ids: set, curr_ids: set):
    hist_file = DATA / f"history_halo_{mode}.json"
    history = []
    if hist_file.exists():
        history = json.loads(hist_file.read_text(encoding="utf-8"))

    cene = [l["cena"] for l in unique if l["cena"]]
    m2s  = [l["m2"]   for l in unique if l["m2"]]

    entry = {
        "date":         str(date.today()),
        "mode":         mode,
        "count":        len(unique),
        "total_raw":    len(raw),
        "total_unique": len(unique),
        "total_dups":   len(raw) - len(unique),
        "diff_new":     len(curr_ids - prev_ids),
        "diff_removed": len(prev_ids - curr_ids),
        "avg_cena":     round(sum(cene)/len(cene)) if cene else None,
        "avg_m2":       round(sum(m2s)/len(m2s), 1) if m2s else None,
    }

    # Zameni red za danas ako već postoji
    history = [h for h in history if h["date"] != entry["date"]]
    history.append(entry)
    hist_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Istorija ažurirana: {hist_file.name}")


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["prodaja", "renta"], default="prodaja")
    args = parser.parse_args()
    mode = args.mode

    if not SCRAPER_API_KEY:
        print("ERROR: SCRAPER_API_KEY nije postavljen.")
        sys.exit(1)

    latest_file = DATA / f"latest_halo_{mode}.json"

    # Prethodni IDs za diff
    prev_ids = set()
    if latest_file.exists():
        prev = json.loads(latest_file.read_text(encoding="utf-8"))
        prev_ids = {l["id"] for l in prev.get("listings", [])}

    print(f"\n=== NB Tracker — Halo Oglasi [{mode}] ===")
    raw = scrape_all(mode)
    unique = compute_dedup(raw)
    curr_ids = {l["id"] for l in unique}

    payload = {
        "date":         str(date.today()),
        "mode":         mode,
        "source":       "halo",
        "total_raw":    len(raw),
        "total_unique": len(unique),
        "diff_new":     list(curr_ids - prev_ids),
        "diff_removed": list(prev_ids - curr_ids),
        "listings":     unique,
    }

    latest_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSačuvano: {latest_file.name}")
    print(f"Ukupno raw: {len(raw)}  |  Unique: {len(unique)}")
    print(f"Novi: {len(curr_ids - prev_ids)}  |  Skinutih: {len(prev_ids - curr_ids)}")

    update_history(mode, raw, unique, prev_ids, curr_ids)


if __name__ == "__main__":
    main()
