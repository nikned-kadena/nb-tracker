"""
NB Tracker — Nekretnine.rs scraper za Novi Beograd (Playwright, lokalni desktop)
Scrape-uje sve stranice prodaje/rente, filtrira po zgradama iz buildings.py.

Pokretanje:
  python scrape_nrs_playwright.py --mode prodaja
  python scrape_nrs_playwright.py --mode renta

Playwright mora biti instaliran:
  pip install playwright
  playwright install chromium
"""

import sys
import json
import re
import argparse
import hashlib
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from buildings import detect_building

# ── URL-ovi ─────────────────────────────────────────────────────────────────
BASE_URLS = {
    "prodaja": "https://www.nekretnine.rs/prodaja-stambenih-nekretnina/beograd/novi-beograd/lista/{page}/",
    "renta":   "https://www.nekretnine.rs/izdavanje-stambenih-nekretnina/beograd/novi-beograd/lista/{page}/",
}

STRUKTURA_MAP = {
    "garsonjera": "garsonjera",
    "jednosoban":  "1.0",
    "jednoiposoban": "1.5",
    "dvosoban":    "2.0",
    "dvoiposoban": "2.5",
    "trosoban":    "3.0",
    "troiposoban": "3.5",
    "četvorosoban": "4.0",
    "četvoroiposoban": "4.5",
    "petosoban":   "5.0",
}


def normalize_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def parse_price(text: str) -> float | None:
    text = text.replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", "")
    m = re.search(r"(\d{4,})", text)
    return float(m.group(1)) if m else None


def parse_m2(text: str) -> float | None:
    # "XXX m²" ili "XXX m2" ili "Xm²"
    m = re.search(r"(\d[\d,\.]*)\s*m[²2]", text, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", "."))
    # Fallback: "XX m" na kraju naslova
    m = re.search(r"(\d+)\s*m\b", text, re.IGNORECASE)
    if m:
        return float(m.group(1))
    return None


def parse_struktura(title: str) -> str:
    t = title.lower()
    for key, val in STRUKTURA_MAP.items():
        if key in t:
            return val
    return "ostalo"


def scrape_page(page_obj, url: str) -> tuple[list[dict], bool]:
    """Scrape jedne NRS stranice pomoću Playwright page objekta."""
    page_obj.goto(url, wait_until="domcontentloaded", timeout=30000)
    page_obj.wait_for_timeout(1500)

    html = page_obj.content()

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    listings = []

    # NRS: oglasi su u article ili div sa data-id ili klasom koja sadrži oglas
    cards = (
        soup.select("article.listing-item") or
        soup.select(".listing-item") or
        soup.select("[class*='listing']") or
        soup.select(".property-list-item")
    )

    # Fallback: oglasi su linkovi na /oglasi/ID/ unutar liste
    if not cards:
        cards = []
        for a in soup.select("a[href*='/oglasi/']"):
            parent = a.find_parent("li") or a.find_parent("article") or a.find_parent("div")
            if parent and parent not in cards:
                cards.append(parent)

    for card in cards:
        # URL oglasa
        link = card.select_one("a[href*='/oglasi/']") or card.select_one("a[href]")
        if not link:
            continue
        href = link.get("href", "")
        if not href:
            continue
        if href.startswith("/"):
            full_url = f"https://www.nekretnine.rs{href}"
        else:
            full_url = href

        # Preskoci ako nije oglas
        if "/oglasi/" not in full_url and "/stambeni-objekti/" not in full_url:
            continue

        listing_id = normalize_id(full_url)

        # Naslov
        title_tag = (
            card.select_one("h2") or
            card.select_one("h3") or
            card.select_one("[class*='title']") or
            link
        )
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Opis (kratak snippet vidljiv na listing stranici)
        desc_tag = card.select_one("p") or card.select_one("[class*='desc']") or card.select_one("[class*='text']")
        desc = desc_tag.get_text(strip=True) if desc_tag else ""

        combined = f"{title} {desc}"
        zgrada = detect_building(combined)
        if not zgrada:
            continue

        # Cena
        price_tag = card.select_one("[class*='price']") or card.select_one("strong")
        price_text = price_tag.get_text(strip=True) if price_tag else ""
        cena = parse_price(price_text)

        # m²
        m2 = parse_m2(title) or parse_m2(desc)
        if m2 is None:
            for span in card.select("span, li, div"):
                txt = span.get_text()
                if "m²" in txt or "m2" in txt:
                    m2 = parse_m2(txt)
                    if m2:
                        break

        cena_m2 = round(cena / m2) if cena and m2 else None
        struktura = parse_struktura(title)

        # Agencija
        agency_tag = card.select_one("[class*='agency']") or card.select_one("img[alt]")
        agencija = None
        if agency_tag:
            agencija = agency_tag.get("alt") or agency_tag.get_text(strip=True)

        listings.append({
            "id":        listing_id,
            "url":       full_url,
            "naslov":    title,
            "opis":      desc[:1000],
            "zgrada":    zgrada,
            "struktura": struktura,
            "cena":      cena,
            "m2":        m2,
            "cena_m2":   cena_m2,
            "agencija":  agencija,
            "izvor":     "nrs",
        })

    # Paginacija
    has_next = bool(soup.select_one("a.next") or soup.select_one("[rel='next']"))
    # NRS alternativa: proveri da li postoji link ka sledećoj stranici
    if not has_next:
        current_url = page_obj.url
        m = re.search(r"/lista/(\d+)/", current_url)
        curr_page = int(m.group(1)) if m else 1
        next_url_pattern = f"/lista/{curr_page + 1}/"
        has_next = bool(soup.select_one(f"a[href*='{next_url_pattern}']"))

    return listings, has_next


def compute_dedup(listings: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for l in listings:
        key = (l["zgrada"], l["m2"], l["cena"])
        if key not in seen:
            seen.add(key)
            unique.append(l)
    return unique


def update_history(mode: str, raw: list, unique: list, prev_ids: set, curr_ids: set):
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
    print(f"  Istorija ažurirana: {hist_file.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["prodaja", "renta"], default="prodaja")
    args = parser.parse_args()
    mode = args.mode

    latest_file = DATA / f"latest_nrs_{mode}.json"

    prev_ids = set()
    if latest_file.exists():
        prev = json.loads(latest_file.read_text(encoding="utf-8"))
        prev_ids = {l["id"] for l in prev.get("listings", [])}

    print(f"\n=== NB Tracker — Nekretnine.rs [{mode}] ===")

    from playwright.sync_api import sync_playwright

    all_raw = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
        )
        pw_page = context.new_page()

        page_num = 1
        while True:
            url = BASE_URLS[mode].format(page=page_num)
            print(f"  NRS [{mode}] stranica {page_num} …", flush=True)
            try:
                listings, has_next = scrape_page(pw_page, url)
            except Exception as e:
                print(f"  GREŠKA na stranici {page_num}: {e}")
                break

            all_raw.extend(listings)
            print(f"    → {len(listings)} relevantnih oglasa")

            if not has_next or len(listings) == 0:
                break
            page_num += 1

        browser.close()

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
    print(f"\nSačuvano: {latest_file.name}")
    print(f"Ukupno raw: {len(all_raw)}  |  Unique: {len(unique)}")
    print(f"Novi: {len(curr_ids - prev_ids)}  |  Skinutih: {len(prev_ids - curr_ids)}")

    update_history(mode, all_raw, unique, prev_ids, curr_ids)


if __name__ == "__main__":
    main()
