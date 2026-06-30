"""
NB Tracker — Halo Oglasi scraper za Novi Beograd, dva koraka (ScraperAPI)

Cloudflare blokira Playwright direktno (Turnstile na paginaciji),
pa koristimo ScraperAPI koji ima svoj anti-bot bypass.

Dva koraka:
1. Listing stranice (sve, preko ?page=N) — skuplja URL-ove oglasa
2. Za svaki oglas — ScraperAPI poziv da procita opis i karakteristike

Pokretanje:
  python scrape_halo_two_step.py --mode prodaja
  python scrape_halo_two_step.py --mode renta

Env var:
  SCRAPER_API_KEY
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

SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY", "")
SCRAPER_URL = "http://api.scraperapi.com"

BASE_URLS = {
    "prodaja": "https://www.halooglasi.com/nekretnine/prodaja-stanova/beograd-novi-beograd",
    "renta":   "https://www.halooglasi.com/nekretnine/izdavanje-stanova/beograd-novi-beograd",
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


def parse_struktura(title: str, desc: str = "") -> str:
    combined = (title + " " + desc).lower()
    txt_map = [
        ("garsonjera", "garsonjera"), ("studio", "garsonjera"),
        ("jednosoban", "garsonjera"), ("jednoiposoban", "1.5"),
        ("dvoiposoban", "2.5"), ("dvosoban", "2.0"),
        ("troiposoban", "3.5"), ("trosoban", "3.0"),
        ("cetvoroiposoban", "4.5"), ("cetvorosoban", "4.0"),
        ("četvoroiposoban", "4.5"), ("četvorosoban", "4.0"),
        ("petosoban", "5.0"),
    ]
    for key, val in txt_map:
        if key in combined:
            return val
    # Numericki format: "3.0, 106m2" Halo pattern
    m = re.search(r"\b(\d+[.,]\d)\b", combined)
    if m:
        num = m.group(1).replace(",", ".")
        if num in SOBE_MAP:
            return SOBE_MAP[num]
    return "ostalo"


def scraper_get(url: str) -> requests.Response:
    params = {"api_key": SCRAPER_API_KEY, "url": url, "render": "false"}
    return requests.get(SCRAPER_URL, params=params, timeout=60)


def get_listing_urls(mode: str, max_pages: int = 50) -> list[str]:
    """Korak 1: skupi sve URL-ove oglasa sa listing stranica."""
    all_urls = []
    seen = set()
    base = BASE_URLS[mode]

    for page_num in range(1, max_pages + 1):
        url = base if page_num == 1 else f"{base}?page={page_num}"
        print(f"  Listing str. {page_num}: {url}", flush=True)

        try:
            resp = scraper_get(url)
        except Exception as e:
            print(f"  GRESKA: {e}")
            break

        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}, stajem.")
            break

        soup = BeautifulSoup(resp.content.decode("utf-8", errors="replace"), "html.parser")
        cards = soup.select(".product-item")

        new_count = 0
        for card in cards:
            link = card.select_one("a[href*='/nekretnine/']")
            if not link:
                continue
            href = link.get("href", "")
            if not href or href in seen:
                continue
            if "/prodaja-stanova/" not in href and "/izdavanje-stanova/" not in href:
                continue
            if href.rstrip("/").endswith(("beograd-novi-beograd")):
                continue
            seen.add(href)
            full_url = f"https://www.halooglasi.com{href}" if href.startswith("/") else href
            all_urls.append(full_url)
            new_count += 1

        print(f"    -> {new_count} novih URL-ova (ukupno: {len(all_urls)}, kartica na str: {len(cards)})")

        if len(cards) == 0:
            print("  Nema vise kartica, stajem.")
            break

        time.sleep(0.3)

    return all_urls


def extract_classified_json(html: str) -> dict | None:
    """
    Halo Oglasi ugradjuje pun JSON podataka oglasa u
    QuidditaEnvironment.CurrentClassified = {...};
    Ovo je najpouzdaniji izvor — strukturirani podaci,
    ne zavisi od HTML/CSS promena na sajtu.
    """
    m = re.search(r"QuidditaEnvironment\.CurrentClassified\s*=\s*(\{.*?\});", html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def scrape_oglas(url: str) -> dict | None:
    """Korak 2: otvori oglas preko ScraperAPI, citaj iz CurrentClassified JSON-a."""
    try:
        resp = scraper_get(url)
    except Exception as e:
        print(f"    GRESKA {url}: {e}")
        return None

    if resp.status_code != 200:
        return None

    html = resp.content.decode("utf-8", errors="replace")
    data = extract_classified_json(html)
    if not data:
        return None

    naslov = data.get("Title", "") or ""
    text_html = data.get("TextHtml", "") or ""
    # Ocisti HTML tagove iz opisa
    opis = re.sub(r"<[^>]+>", " ", text_html)
    opis = re.sub(r"\s+", " ", opis).strip()

    other = data.get("OtherFields", {}) or {}

    # Da li je oglas istekao (ValidTo u proslosti) — preskoci stare oglase
    valid_to = data.get("ValidTo", "")
    if valid_to:
        try:
            from datetime import datetime as _dt
            vt = _dt.fromisoformat(valid_to.replace("Z", "+00:00"))
            if vt < _dt.now(vt.tzinfo):
                return None  # istekao oglas, placeholder podaci
        except Exception:
            pass

    combined = f"{naslov} {opis}"
    zgrada = detect_building(combined)
    if not zgrada:
        return None

    # Strukturirani podaci direktno iz OtherFields
    cena = other.get("cena_d") or other.get("defaultunit_cena_d")
    m2 = other.get("kvadratura_d") or other.get("defaultunit_kvadratura_d")
    broj_soba = other.get("broj_soba_s")

    struktura = "ostalo"
    if broj_soba:
        bs = str(broj_soba).strip()
        if bs in SOBE_MAP:
            struktura = SOBE_MAP[bs]
        else:
            struktura = parse_struktura(naslov, opis)
    else:
        struktura = parse_struktura(naslov, opis)

    cena_m2 = round(cena / m2) if cena and m2 and m2 > 5 else None

    # Agencija — AdvertiserId postoji, ali ime agencije obicno nije u ovom JSON-u
    # Probaj iz HTML-a kao fallback
    agencija = None
    soup = BeautifulSoup(html, "html.parser")
    agency_tag = soup.select_one(".panel-user-name, [class*='advertiser'] [class*='name'], .seller-name")
    if agency_tag:
        agencija = agency_tag.get_text(strip=True) or None
    oglasivac_tip = other.get("oglasivac_nekretnine_s", "")
    if not agencija and oglasivac_tip and oglasivac_tip.lower() != "agencija":
        agencija = None  # privatno lice, ostaje None

    listing_id = normalize_id(url)

    return {
        "id":        listing_id,
        "url":       url,
        "naslov":    naslov,
        "opis":      opis[:1200],
        "zgrada":    zgrada,
        "struktura": struktura,
        "cena":      cena,
        "m2":        m2,
        "cena_m2":   cena_m2,
        "agencija":  agencija,
        "izvor":     "halo",
    }


def compute_dedup(listings):
    seen = set()
    unique = []
    for l in listings:
        m2_rounded = round(l["m2"]) if l["m2"] else None
        key = (l["zgrada"], m2_rounded, l["cena"])
        if key not in seen:
            seen.add(key)
            unique.append(l)
    return unique


def update_history(mode, raw, unique, prev_ids, curr_ids):
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
    history = [h for h in history if h["date"] != entry["date"]]
    history.append(entry)
    hist_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Istorija azurirana: {hist_file.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["prodaja", "renta"], default="prodaja")
    parser.add_argument("--max-pages", type=int, default=50)
    args = parser.parse_args()
    mode = args.mode

    if not SCRAPER_API_KEY:
        print("ERROR: SCRAPER_API_KEY nije postavljen.")
        sys.exit(1)

    latest_file = DATA / f"latest_halo_{mode}.json"
    prev_ids = set()
    if latest_file.exists():
        prev = json.loads(latest_file.read_text(encoding="utf-8"))
        prev_ids = {l["id"] for l in prev.get("listings", [])}

    print(f"\n=== NB Tracker - Halo Oglasi [dva koraka] [{mode}] ===")

    print(f"\n[Korak 1] Skupljam URL-ove oglasa...")
    all_urls = get_listing_urls(mode, args.max_pages)
    print(f"\nUkupno URL-ova: {len(all_urls)}")

    print(f"\n[Korak 2] Scrape-ujem {len(all_urls)} oglasa...")
    all_raw = []
    for i, url in enumerate(all_urls, 1):
        if i % 20 == 0:
            print(f"  {i}/{len(all_urls)} oglasa ({len(all_raw)} relevantnih)...", flush=True)
        listing = scrape_oglas(url)
        if listing:
            all_raw.append(listing)
        time.sleep(0.2)

    unique = compute_dedup(all_raw)
    curr_ids = {l["id"] for l in unique}

    payload = {
        "date":         str(date.today()),
        "mode":         mode,
        "source":       "halo",
        "total_raw":    len(all_raw),
        "total_unique": len(unique),
        "diff_new":     list(curr_ids - prev_ids),
        "diff_removed": list(prev_ids - curr_ids),
        "listings":     unique,
    }

    latest_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSacuvano: {latest_file.name}")
    print(f"URL-ova: {len(all_urls)} | Relevantnih: {len(all_raw)} | Unique: {len(unique)}")
    print(f"Novi: {len(curr_ids - prev_ids)} | Skinutih: {len(prev_ids - curr_ids)}")
    update_history(mode, all_raw, unique, prev_ids, curr_ids)


if __name__ == "__main__":
    main()
