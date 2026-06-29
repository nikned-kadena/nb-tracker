"""
NB Tracker — Nekretnine.rs scraper za Novi Beograd (requests + BeautifulSoup)
Pokrece se kroz GitHub Actions, ne zahteva Playwright.

NRS se renderuje staticki pa nema potrebe za JS renderom.

Pokretanje:
  python scrape_nrs.py --mode prodaja
  python scrape_nrs.py --mode renta
"""

import os
import sys
import json
import re
import argparse
import hashlib
import time
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from buildings import detect_building

BASE_URLS = {
    "prodaja": "https://www.nekretnine.rs/prodaja-stambenih-nekretnina/beograd/novi-beograd/lista/{page}/",
    "renta":   "https://www.nekretnine.rs/izdavanje-stambenih-nekretnina/beograd/novi-beograd/lista/{page}/",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "sr-RS,sr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SOBE_MAP = {
    "0.5": "garsonjera", "1.0": "1.0", "1.5": "1.5",
    "2.0": "2.0", "2.5": "2.5", "3.0": "3.0", "3.5": "3.5",
    "4.0": "4.0", "4.5": "4.5", "5.0": "5.0",
}


def normalize_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def parse_price(text: str) -> float | None:
    text = text.replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", "")
    m = re.search(r"(\d{4,})", text)
    return float(m.group(1)) if m else None


def parse_m2(text: str) -> float | None:
    m = re.search(r"(\d[\d\.]*)\s*m[²2]", text, re.IGNORECASE)
    if m:
        try:
            val = float(m.group(1))
            if 5 < val < 1000:
                return val
        except:
            pass
    return None


def parse_struktura(title: str, desc: str) -> str:
    """
    Tri nivoa parsiranja:
    1. NRS page title format: "Trosobni stan", "Dvosobni stan", "Garsonjera"
    2. Opis: "2.0, 56m2" ili "po strukturi 3.0"
    3. Tekstualni fallback
    """
    combined = (title + " " + desc).lower()

    # NRS u naslovu uvek pise tip: "Trosobni stan X, Y, Beograd"
    nrs_map = [
        ("garsonjera", "garsonjera"),
        ("jednoiposobni", "1.5"), ("jednosobni", "1.0"),
        ("dvoiposobni", "2.5"),   ("dvosobni", "2.0"),
        ("troiposobni", "3.5"),   ("trosobni", "3.0"),
        ("cetvoroiposobni", "4.5"), ("cetvorosobni", "4.0"),
        ("petosobni", "5.0"),
        # Bez deklinacije
        ("garsonjera", "garsonjera"),
        ("jednoiposoban", "1.5"), ("jednosoban", "1.0"),
        ("dvoiposoban", "2.5"),   ("dvosoban", "2.0"),
        ("troiposoban", "3.5"),   ("trosoban", "3.0"),
        ("cetvoroiposoban", "4.5"), ("cetvorosoban", "4.0"),
        ("petosoban", "5.0"),
        ("studio", "garsonjera"),
    ]
    for key, val in nrs_map:
        if key in combined:
            return val

    # Numericki: "po strukturi 2.0" ili standalone "2.0, 56m2"
    m = re.search(r"(?:strukturi\s+)?(\d+[.,]\d)\b", combined)
    if m:
        num = m.group(1).replace(",", ".")
        if num in SOBE_MAP:
            return SOBE_MAP[num]

    return "ostalo"


SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")
SCRAPER_URL = "http://api.scraperapi.com"


def fetch_page(url: str) -> BeautifulSoup | None:
    """Koristi ScraperAPI da zaobidze Cloudflare/bot detekciju na NRS."""
    try:
        params = {"api_key": SCRAPER_API_KEY, "url": url, "render": "false"}
        resp = requests.get(SCRAPER_URL, params=params, timeout=60)
        if resp.status_code == 200:
            return BeautifulSoup(resp.content.decode("utf-8", errors="replace"), "html.parser")
        print(f"  ScraperAPI HTTP {resp.status_code}: {url}")
        return None
    except Exception as e:
        print(f"  Greska: {e}")
        return None


def scrape_page(url: str) -> tuple[list[dict], bool]:
    soup = fetch_page(url)
    if not soup:
        return [], False

    listings = []

    # NRS listing kartice
    cards = (
        soup.select("div.offer-body") or
        soup.select("article.real-estate-ad") or
        soup.select("[class*='offer']") or
        soup.select("li.offer")
    )

    # Fallback — svi linkovi ka /oglasi/
    if not cards:
        seen_urls = set()
        for a in soup.select("a[href*='/oglasi/']"):
            href = a.get("href", "")
            if href in seen_urls:
                continue
            seen_urls.add(href)

            full_url = f"https://www.nekretnine.rs{href}" if href.startswith("/") else href
            listing_id = normalize_id(full_url)

            # Nadji parent kontejner
            parent = a.find_parent("article") or a.find_parent("li") or a.find_parent("div")
            if not parent:
                continue

            title = a.get_text(strip=True) or a.get("title", "")
            if not title:
                continue

            # Opis iz parent-a
            desc_tag = parent.select_one("p, [class*='desc'], [class*='text']")
            desc = desc_tag.get_text(strip=True) if desc_tag else ""

            combined = f"{title} {desc}"
            zgrada = detect_building(combined)
            if not zgrada:
                continue

            # Cena
            price_tag = parent.select_one("[class*='price'], strong")
            cena = parse_price(price_tag.get_text()) if price_tag else None

            # m2
            m2 = parse_m2(title) or parse_m2(desc)

            # Agencija
            img = parent.select_one("img[alt]")
            agencija = img.get("alt") if img else None

            cena_m2 = round(cena / m2) if cena and m2 and m2 > 5 else None
            struktura = parse_struktura(title, desc)

            listings.append({
                "id":        listing_id,
                "url":       full_url,
                "naslov":    title,
                "opis":      combined[:1200],
                "zgrada":    zgrada,
                "struktura": struktura,
                "cena":      cena,
                "m2":        m2,
                "cena_m2":   cena_m2,
                "agencija":  agencija,
                "izvor":     "nrs",
            })
        # Paginacija
        has_next = bool(soup.select_one("a[rel='next']") or soup.select_one("a.next"))
        # NRS fallback paginacija — trazi link ka sledecoj strani
        if not has_next:
            current_m = re.search(r"/lista/(\d+)/", url)
            curr_p = int(current_m.group(1)) if current_m else 1
            has_next = bool(soup.find("a", href=re.compile(f"/lista/{curr_p+1}/")))
        return listings, has_next

    # Ako smo nasli cards direktno
    for card in cards:
        link = card.select_one("a[href*='/oglasi/']") or card.select_one("a[href]")
        if not link:
            continue
        href = link.get("href", "")
        full_url = f"https://www.nekretnine.rs{href}" if href.startswith("/") else href
        listing_id = normalize_id(full_url)

        title_tag = card.select_one("h2, h3, [class*='title']") or link
        title = title_tag.get_text(strip=True)

        desc_tag = card.select_one("p, [class*='desc']")
        desc = desc_tag.get_text(strip=True) if desc_tag else ""

        combined = f"{title} {desc}"
        zgrada = detect_building(combined)
        if not zgrada:
            continue

        price_tag = card.select_one("[class*='price'], strong")
        cena = parse_price(price_tag.get_text()) if price_tag else None
        m2 = parse_m2(title) or parse_m2(desc)
        cena_m2 = round(cena / m2) if cena and m2 and m2 > 5 else None
        struktura = parse_struktura(title, desc)
        img = card.select_one("img[alt]")
        agencija = img.get("alt") if img else None

        listings.append({
            "id": listing_id, "url": full_url,
            "naslov": title, "opis": combined[:1200],
            "zgrada": zgrada, "struktura": struktura,
            "cena": cena, "m2": m2, "cena_m2": cena_m2,
            "agencija": agencija, "izvor": "nrs",
        })

    has_next = bool(soup.select_one("a[rel='next']") or soup.select_one("a.next"))
    if not has_next:
        current_m = re.search(r"/lista/(\d+)/", url)
        curr_p = int(current_m.group(1)) if current_m else 1
        has_next = bool(soup.find("a", href=re.compile(f"/lista/{curr_p+1}/")))

    return listings, has_next


def compute_dedup(listings):
    seen = set()
    unique = []
    for l in listings:
        key = (l["zgrada"], l["m2"], l["cena"])
        if key not in seen:
            seen.add(key)
            unique.append(l)
    return unique


def update_history(mode, raw, unique, prev_ids, curr_ids):
    hist_file = DATA / f"history_nrs_{mode}.json"
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
    history = [h for h in history if h["date"] != entry["date"]]
    history.append(entry)
    hist_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Istorija azurirana: {hist_file.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["prodaja", "renta"], default="prodaja")
    parser.add_argument("--max-pages", type=int, default=80)
    args = parser.parse_args()
    mode = args.mode

    latest_file = DATA / f"latest_nrs_{mode}.json"
    prev_ids = set()
    if latest_file.exists():
        prev = json.loads(latest_file.read_text(encoding="utf-8"))
        prev_ids = {l["id"] for l in prev.get("listings", [])}

    print(f"\n=== NB Tracker — Nekretnine.rs [{mode}] ===")

    all_raw = []
    page_num = 1

    while page_num <= args.max_pages:
        url = BASE_URLS[mode].format(page=page_num)
        print(f"  NRS [{mode}] str. {page_num} ...", flush=True)

        listings, has_next = scrape_page(url)
        all_raw.extend(listings)
        print(f"    -> {len(listings)} relevantnih (ukupno: {len(all_raw)})")

        if not has_next or len(listings) == 0:
            print("  Nema vise stranica.")
            break

        page_num += 1
        time.sleep(0.5)  # Courtesy delay

    unique = compute_dedup(all_raw)
    curr_ids = {l["id"] for l in unique}

    payload = {
        "date":         str(date.today()),
        "mode":         mode,
        "source":       "nrs",
        "total_raw":    len(all_raw),
        "total_unique": len(unique),
        "diff_new":     list(curr_ids - prev_ids),
        "diff_removed": list(prev_ids - curr_ids),
        "listings":     unique,
    }

    latest_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSacuvano: {latest_file.name}")
    print(f"Raw: {len(all_raw)}  |  Unique: {len(unique)}")
    print(f"Novi: {len(curr_ids - prev_ids)}  |  Skinutih: {len(prev_ids - curr_ids)}")
    update_history(mode, all_raw, unique, prev_ids, curr_ids)


if __name__ == "__main__":
    main()
