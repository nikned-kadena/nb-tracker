"""
NB Tracker — Nekretnine.rs scraper za Novi Beograd (Playwright, lokalni)

Dva koraka:
1. Listing stranice — skuplja sve URL-ove oglasa
2. Za svaki oglas — otvara stranicu i cita meta-description + podatke

Pokretanje:
  python scrape_nrs_playwright.py --mode prodaja
  python scrape_nrs_playwright.py --mode renta
"""

import sys
import json
import re
import argparse
import hashlib
import time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

sys.path.insert(0, str(Path(__file__).parent))
from buildings import detect_building

# URL samo za stanove (ne kuce)
# Paginacija: ?pag=2, ?pag=3 itd.
BASE_URLS = {
    "prodaja": {
        1:   "https://www.nekretnine.rs/prodaja-stanova/beograd/novi-beograd/",
        "n": "https://www.nekretnine.rs/prodaja-stanova/beograd/novi-beograd/?pag={page}",
    },
    "renta": {
        1:   "https://www.nekretnine.rs/izdavanje-stanova/beograd/novi-beograd/",
        "n": "https://www.nekretnine.rs/izdavanje-stanova/beograd/novi-beograd/?pag={page}",
    },
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
    # Pokusaj i bez m² znaka: "| 196 m²" pattern u page title
    m2 = re.search(r"\|\s*(\d+)\s*m", text, re.IGNORECASE)
    if m2:
        try:
            val = float(m2.group(1))
            if 5 < val < 1000:
                return val
        except:
            pass
    return None


def parse_struktura(title: str, desc: str = "") -> str:
    combined = (title + " " + desc).lower()
    nrs_map = [
        ("garsonjera", "garsonjera"), ("studio", "garsonjera"),
        # Sa dijakriticima (NRS pise ovako u naslovima)
        ("jednoiposobni", "1.5"),  ("jednosobni", "1.0"),
        ("dvoiposobni", "2.5"),    ("dvosobni", "2.0"),
        ("troiposobni", "3.5"),    ("trosobni", "3.0"),
        ("četvoroiposobni", "4.5"),("četvorosobni", "4.0"),
        ("petosobni", "5.0"),      ("šesoban", "5.0"),
        # Bez dijakritika (fallback)
        ("jednoiposoban", "1.5"),  ("jednosoban", "1.0"),
        ("dvoiposoban", "2.5"),    ("dvosoban", "2.0"),
        ("troiposoban", "3.5"),    ("trosoban", "3.0"),
        ("cetvoroiposoban", "4.5"),("cetvorosoban", "4.0"),
        ("petosoban", "5.0"),
    ]
    for key, val in nrs_map:
        if key in combined:
            return val
    # Numericki: "| 3 sobe |" u page title
    m = re.search(r"\|\s*(\d+)\s*sob", combined)
    if m:
        n = int(m.group(1))
        sobe_to_str = {1: "1.0", 2: "2.0", 3: "3.0", 4: "4.0", 5: "5.0"}
        if n in sobe_to_str:
            return sobe_to_str[n]
    m2 = re.search(r"\b(\d+[.,]\d)\b", combined)
    if m2:
        num = m2.group(1).replace(",", ".")
        if num in SOBE_MAP:
            return SOBE_MAP[num]
    return "ostalo"


def get_listing_urls(pw_page, mode: str, max_pages: int = 40) -> list[str]:
    """Korak 1: Skupi sve URL-ove oglasa sa listing stranica."""
    all_urls = []
    seen = set()

    for page_num in range(1, max_pages + 1):
        if page_num == 1:
            url = BASE_URLS[mode][1]
        else:
            url = BASE_URLS[mode]["n"].format(page=page_num)

        print(f"  Listing str. {page_num}: {url}", flush=True)
        try:
            pw_page.goto(url, wait_until="networkidle", timeout=30000)
            pw_page.wait_for_timeout(1500)
        except Exception as e:
            print(f"  GRESKA: {e}")
            break

        html = pw_page.content()
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Skupi /oglasi/ linkove
        links = soup.select("a[href*='/oglasi/']")
        new_count = 0
        for a in links:
            href = a.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)
            full_url = f"https://www.nekretnine.rs{href}" if href.startswith("/") else href
            all_urls.append(full_url)
            new_count += 1

        print(f"    -> {new_count} novih URL-ova (ukupno: {len(all_urls)})")

        # Paginacija
        has_next = bool(
            soup.select_one("a[rel='next']") or
            soup.find("a", href=re.compile(r"[?&]pag=" + str(page_num + 1))) or
            soup.find("a", string=str(page_num + 1))
        )
        if page_num == 1:
            has_next = bool(
                soup.find("a", href=re.compile(r"[?&]pag=2")) or
                soup.find("a", string="2")
            )

        if not has_next or new_count == 0:
            print(f"  Nema vise listing stranica.")
            break

    return all_urls


def scrape_oglas(pw_page, url: str) -> dict | None:
    """Korak 2: Otvori oglas i izvuci podatke iz meta tagova i sadrzaja."""
    try:
        pw_page.goto(url, wait_until="domcontentloaded", timeout=20000)
        pw_page.wait_for_timeout(800)
    except Exception as e:
        print(f"    GRESKA {url}: {e}")
        return None

    html = pw_page.content()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Meta description — sadrzi ime zgrade i opis
    meta_desc = ""
    meta_tag = soup.select_one("meta[name='description']") or soup.select_one("meta[property='og:description']")
    if meta_tag:
        meta_desc = meta_tag.get("content", "")

    # Page title — NRS format: "Trosobni stan ... | 3 sobe | 85 m²"
    page_title = soup.title.get_text(strip=True) if soup.title else ""

    # H1 naslov oglasa
    h1 = soup.select_one("h1")
    naslov = h1.get_text(strip=True) if h1 else ""

    # Cena
    cena = None
    price_tag = soup.select_one("[class*='price'], [class*='Price']")
    if price_tag:
        cena = parse_price(price_tag.get_text())
    if not cena:
        m = re.search(r"€\s*([\d\.\s]+)", meta_desc)
        if m:
            cena = parse_price(m.group(1))

    # m2 — pet fallback izvora (lekcija iz BnV trackera)
    m2 = None

    # Fallback 1: NRS options meta tag "| 3 sobe | 85 m²" — najpouzdanije
    meta_opts = soup.select_one("meta[name='nekretnine_rs:options']")
    if meta_opts:
        m2 = parse_m2(meta_opts.get("content", ""))

    # Fallback 2: page title "| XXX m²" format
    if not m2:
        pt_m = re.search(r"\|\s*(\d+[\.,]?\d*)\s*m", page_title, re.IGNORECASE)
        if pt_m:
            try:
                val = float(pt_m.group(1).replace(",", "."))
                if 5 < val < 1000:
                    m2 = val
            except:
                pass

    # Fallback 3: structured data — "Površina XXX m²" ili "XXX m²" u karakteristikama
    if not m2:
        # Pokusaj direktno iz teksta cele stranice
        full_text = soup.get_text(" ", strip=True)
        # Trazi "Površina" pa broj
        surf_m = re.search(r"Povr[sš]ina\s*[:.]?\s*(\d+[\.,]?\d*)\s*m", full_text, re.IGNORECASE)
        if surf_m:
            try:
                val = float(surf_m.group(1).replace(",", "."))
                if 5 < val < 1000:
                    m2 = val
            except:
                pass
        # Fallback: "Stambena površina" ili "Neto površina"
        if not m2:
            surf_m2 = re.search(r"(?:Stambena|Neto|Bruto|Ukupna)\s+povr[sš]ina\s*[:.]?\s*(\d+[\.,]?\d*)\s*m", 
                               full_text, re.IGNORECASE)
            if surf_m2:
                try:
                    val = float(surf_m2.group(1).replace(",", "."))
                    if 5 < val < 1000:
                        m2 = val
                except:
                    pass

    # Fallback 4: H1/H2/H3 headinzi — agencije cesto pisu "Stan 85m2"
    if not m2:
        for hsel in ["h1", "h2", "h3"]:
            for h in soup.select(hsel):
                m2 = parse_m2(h.get_text())
                if m2:
                    break
            if m2:
                break

    # Fallback 5: meta description
    if not m2:
        m2 = parse_m2(meta_desc)

    # Fallback 6: bilo koji element sa brojem i m²
    if not m2:
        for txt in soup.find_all(string=re.compile(r"\d+\s*m[²2]", re.IGNORECASE)):
            val = parse_m2(txt)
            if val and 10 < val < 500:
                m2 = val
                break

    # Agencija — dva pouzdana izvora na NRS stranici oglasa
    agencija = None
    IGNORE = {
        "user male", "user female", "user",
        "agent male", "agent female", "agent",
        "korisnik muski", "korisnik zenski",
        "agent muski", "agent zenski",
        "agencije", "agencija", "",
    }

    # Izvor 1: img[src*='/agenti/'] — alt tag sadrzi ime agencije
    # NRS ima dva takva img-a: prvi je genericki (prazan alt), drugi je agencija
    for img in soup.select("img[src*='/agenti/']"):
        alt = img.get("alt", "").strip()
        if alt.lower() not in IGNORE:
            agencija = alt
            break

    # Izvor 2: a[href*='/agencije-za-nekretnine/'] — direktni text node
    # list(a.strings)[0] daje samo ime, bez "Prikaži telefon" child elemenata
    if not agencija:
        for a in soup.select("a[href*='/agencije-za-nekretnine/']"):
            strings = [s.strip() for s in a.strings if s.strip()]
            if strings:
                name = strings[0]  # Uvek prvi string = ime agencije
                if name.lower() not in IGNORE and len(name) > 3:
                    agencija = name[:80]
                    break

    # Detekcija zgrade — iz meta_desc koji sadrzi pun opis
    combined = f"{naslov} {meta_desc} {page_title}"
    zgrada = detect_building(combined)

    if not zgrada:
        return None

    struktura = parse_struktura(naslov, meta_desc + " " + page_title)
    cena_m2 = round(cena / m2) if cena and m2 and m2 > 5 else None
    listing_id = normalize_id(url)

    return {
        "id":        listing_id,
        "url":       url,
        "naslov":    naslov,
        "opis":      meta_desc[:1200],
        "zgrada":    zgrada,
        "struktura": struktura,
        "cena":      cena,
        "m2":        m2,
        "cena_m2":   cena_m2,
        "agencija":  agencija,
        "izvor":     "nrs",
    }


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
    parser.add_argument("--max-pages", type=int, default=40)
    args = parser.parse_args()
    mode = args.mode

    latest_file = DATA / f"latest_nrs_{mode}.json"
    prev_ids = set()
    if latest_file.exists():
        prev = json.loads(latest_file.read_text(encoding="utf-8"))
        prev_ids = {l["id"] for l in prev.get("listings", [])}

    print(f"\n=== NB Tracker - NRS [{mode}] ===")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        pw_page = context.new_page()

        # KORAK 1: Skupi sve URL-ove
        print(f"\n[Korak 1] Skupljam URL-ove oglasa...")
        all_urls = get_listing_urls(pw_page, mode, args.max_pages)
        print(f"\nUkupno URL-ova: {len(all_urls)}")

        # KORAK 2: Otvori svaki oglas
        print(f"\n[Korak 2] Scrape-ujem {len(all_urls)} oglasa...")
        all_raw = []
        for i, url in enumerate(all_urls, 1):
            if i % 10 == 0:
                print(f"  {i}/{len(all_urls)} oglasa ({len(all_raw)} relevantnih)...", flush=True)
            listing = scrape_oglas(pw_page, url)
            if listing:
                all_raw.append(listing)
            time.sleep(0.3)  # Courtesy delay

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
    print(f"\nSacuvano: {latest_file.name}")
    print(f"Ukupno URL-ova: {len(all_urls)} | Relevantnih: {len(all_raw)} | Unique: {len(unique)}")
    print(f"Novi: {len(curr_ids - prev_ids)} | Skinutih: {len(prev_ids - curr_ids)}")
    update_history(mode, all_raw, unique, prev_ids, curr_ids)


if __name__ == "__main__":
    main()
