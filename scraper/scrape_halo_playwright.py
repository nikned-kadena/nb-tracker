"""
NB Tracker — Halo Oglasi scraper za Novi Beograd (Playwright, lokalni desktop)

Resava dva problema ScraperAPI verzije:
1. Paginacija — hvata sve stranice sa JS renderom
2. Struktura — cita "Broj soba" iz features liste ili "X.0, YYm2" pattern iz opisa

Pokretanje:
  python scrape_halo_playwright.py --mode prodaja
  python scrape_halo_playwright.py --mode renta
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

BASE_URLS = {
    "prodaja": "https://www.halooglasi.com/nekretnine/prodaja-stanova/beograd-novi-beograd",
    "renta":   "https://www.halooglasi.com/nekretnine/izdavanje-stanova/beograd-novi-beograd",
}

# Mapa broj soba -> struktura kod
SOBE_MAP = {
    "0.5": "garsonjera", "1.0": "1.0", "1.5": "1.5",
    "2.0": "2.0", "2.5": "2.5", "3.0": "3.0", "3.5": "3.5",
    "4.0": "4.0", "4.5": "4.5", "5.0": "5.0",
}


def normalize_id(slug: str) -> str:
    return hashlib.md5(slug.encode()).hexdigest()[:12]


def parse_price(text: str) -> float | None:
    text = text.replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", "")
    m = re.search(r"(\d{4,})", text)
    return float(m.group(1)) if m else None


def parse_m2(text: str) -> float | None:
    m = re.search(r"(\d[\d\.]*)\s*m[²2]", text, re.IGNORECASE)
    if m:
        try:
            return float(m.group(1))
        except:
            pass
    return None


def parse_struktura(title: str, desc: str, features_text: str) -> str:
    """
    Pokusava da detektuje strukturu iz tri izvora, po prioritetu:
    1. Features lista: "Broj soba: 3.0" (najpouzdanije — strukturirani podatak)
    2. Opis kartice: "3.0, 106m2" ili "4.0, 134m2 (terasa...)" pattern
    3. Naslov: tekstualni ("Trosoban") ili numericki ("3.0")
    """

    # ── 1. Features lista (najpouzdanije) ─────────────────────────────────
    # Trazi "3.0" ili "2.5" odmah posle "Broj soba" labele
    feat_m = re.search(r"broj\s*soba[^\d]*(\d+[.,]\d)", features_text, re.IGNORECASE)
    if feat_m:
        num = feat_m.group(1).replace(",", ".")
        if num in SOBE_MAP:
            return SOBE_MAP[num]

    # ── 2. Opis kartice: "X.0, YYm2" ili "X.0 | YYm2" pattern ─────────────
    # Halo format: "Bulevar... 3.0, 106m2 (lođe 8m2), 4/7, CG, lift..."
    desc_m = re.search(r"\b(\d+[.,]\d)\s*[,|]\s*\d+\s*m", desc, re.IGNORECASE)
    if desc_m:
        num = desc_m.group(1).replace(",", ".")
        if num in SOBE_MAP:
            return SOBE_MAP[num]

    # ── 3. Naslov — tekstualni format ──────────────────────────────────────
    t = (title + " " + desc).lower()
    txt_map = [
        ("garsonjera", "garsonjera"),
        ("jednoiposoban", "1.5"), ("jednosoban", "1.0"),
        ("dvoiposoban", "2.5"),   ("dvosoban", "2.0"),
        ("troiposoban", "3.5"),   ("trosoban", "3.0"),
        ("cetvoroiposoban", "4.5"), ("cetvorosoban", "4.0"),
        ("petosoban", "5.0"),     ("visesoban", "5.0"),
        ("studio", "garsonjera"),
    ]
    for key, val in txt_map:
        if key in t:
            return val

    # ── 4. Naslov — numericki format ────────────────────────────────────────
    # "Izuzetan 4.0 stan", "Novo, Soul 64, 2.0"
    num_m = re.search(r"\b(\d+[.,]\d)\b", t)
    if num_m:
        num = num_m.group(1).replace(",", ".")
        if num in SOBE_MAP:
            return SOBE_MAP[num]

    return "ostalo"


def scrape_page(pw_page, url: str) -> tuple[list[dict], bool]:
    from bs4 import BeautifulSoup

    pw_page.goto(url, wait_until="networkidle", timeout=45000)
    try:
        pw_page.wait_for_selector("li.product-item", timeout=15000)
    except:
        pass
    pw_page.wait_for_timeout(2000)

    soup = BeautifulSoup(pw_page.content(), "html.parser")
    cards = soup.select("li.product-item")

    listings = []
    for card in cards:
        link_tag = card.select_one("a[href*='/nekretnine/']")
        if not link_tag:
            continue
        href = link_tag.get("href", "")
        # Preskoci stranicne linkove (lista, pretraga)
        if not href or "/prodaja-stanova/" not in href and "/izdavanje-stanova/" not in href:
            continue
        # Preskoci ako je samo kategorija, ne oglas (nema broj na kraju)
        if href.rstrip("/").endswith("beograd-novi-beograd"):
            continue

        full_url = f"https://www.halooglasi.com{href}" if href.startswith("/") else href
        slug = href.strip("/").split("/")[-1]
        listing_id = normalize_id(slug)

        # Naslov
        title_tag = card.select_one("h3.product-title, .product-title")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # Opis
        desc_tag = card.select_one(".product-description, .short-description")
        desc = desc_tag.get_text(strip=True) if desc_tag else ""

        # Features lista — kljucni izvor za sobe i m2
        features_text = ""
        m2_from_features = None
        for feat in card.select("ul.product-features li"):
            legend = feat.select_one("span.legend")
            val_el  = feat.select_one("div.value-wrapper, .value")
            if not legend or not val_el:
                continue
            legend_txt = legend.get_text(strip=True).lower()
            val_txt    = val_el.get_text(strip=True)
            features_text += f" {legend_txt}: {val_txt}"
            # m2 iz features
            if ("kvadrat" in legend_txt or "povr" in legend_txt or
                    legend_txt.strip() in ("m2", "m²", "kvadratura")):
                m2_from_features = parse_m2(val_txt)

        combined = f"{title} {desc} {features_text}"

        # Detekcija zgrade
        zgrada = detect_building(combined)
        if not zgrada:
            continue

        # Struktura — sva tri izvora
        struktura = parse_struktura(title, desc, features_text)

        # Cena
        price_tag = card.select_one(".price-box, [class*='price']")
        price_text = price_tag.get_text(strip=True) if price_tag else ""
        cena = parse_price(price_text)

        # m2 — prioritet: features > naslov > opis
        m2 = m2_from_features or parse_m2(title) or parse_m2(desc)

        cena_m2 = round(cena / m2) if cena and m2 and m2 > 5 else None

        # Agencija
        agency_tag = card.select_one(".username, [class*='username']")
        agencija = agency_tag.get_text(strip=True) if agency_tag else None

        listings.append({
            "id":        listing_id,
            "slug":      slug,
            "url":       full_url,
            "naslov":    title,
            "opis":      (desc + " " + features_text).strip()[:1200],
            "zgrada":    zgrada,
            "struktura": struktura,
            "cena":      cena,
            "m2":        m2,
            "cena_m2":   cena_m2,
            "agencija":  agencija,
            "izvor":     "halo",
        })

    # Paginacija
    has_next = bool(
        soup.select_one("a.next") or
        soup.select_one("[rel='next']") or
        soup.select_one("li.next a") or
        soup.select_one(".pagination .next")
    )
    if not has_next and len(cards) >= 20:
        # Proveri postoji li paginacija sa sledecim brojem
        pagination = soup.select_one(".pagination, [class*='paginat']")
        if pagination:
            active = pagination.select_one(".active, [class*='active']")
            if active and active.find_next_sibling():
                has_next = True

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
    parser.add_argument("--max-pages", type=int, default=60)
    args = parser.parse_args()
    mode = args.mode

    latest_file = DATA / f"latest_halo_{mode}.json"
    prev_ids = set()
    if latest_file.exists():
        prev = json.loads(latest_file.read_text(encoding="utf-8"))
        prev_ids = {l["id"] for l in prev.get("listings", [])}

    print(f"\n=== NB Tracker — Halo Oglasi Playwright [{mode}] ===")

    from playwright.sync_api import sync_playwright

    all_raw = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        pw_page = context.new_page()

        page_num = 1
        base_url = BASE_URLS[mode]

        while page_num <= args.max_pages:
            url = base_url if page_num == 1 else f"{base_url}?page={page_num}"
            print(f"  Halo [{mode}] str. {page_num} ...", flush=True)

            try:
                listings, has_next = scrape_page(pw_page, url)
            except Exception as e:
                print(f"  GRESKA str. {page_num}: {e}")
                break

            all_raw.extend(listings)
            print(f"    -> {len(listings)} relevantnih (ukupno: {len(all_raw)})")

            if not has_next or len(listings) == 0:
                print("  Nema vise stranica.")
                break
            page_num += 1

        browser.close()

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
    print(f"Raw: {len(all_raw)}  |  Unique: {len(unique)}")
    print(f"Novi: {len(curr_ids - prev_ids)}  |  Skinutih: {len(prev_ids - curr_ids)}")
    update_history(mode, all_raw, unique, prev_ids, curr_ids)


if __name__ == "__main__":
    main()
