"""
NB Tracker — Halo Oglasi scraper za Novi Beograd, dva koraka (ScraperAPI)
v2 — INKREMENTALNI Korak 2 (04.07.2026)

Cloudflare blokira Playwright direktno (Turnstile na paginaciji),
pa koristimo ScraperAPI koji ima svoj anti-bot bypass.

Dva koraka:
1. Listing stranice (sve, preko ?page=N) — skuplja URL-ove oglasa + cene sa kartica
2. SAMO ZA NOVE oglase — ScraperAPI poziv da procita opis i karakteristike.
   Poznati oglasi dolaze iz kesa (data/cache_halo_{mode}.json), a cena im se
   svaki dan osvezava sa listing kartice — bez dodatnih requestova.

Zasto: halooglasi.com kosta 10 ScraperAPI kredita PO REQUESTU. Stari pristup
(svih ~1.000 oglasa dnevno) = ~20.000 kredita/dan. Inkrementalni = ~1.300/dan.

Kes pamti i NERELEVANTNE oglase (marker bez podataka) — inace bismo ~800
nerelevantnih placali svaki dan iznova.

Full refresh (ceo set iznova, kes se gradi od nule):
  - automatski NEDELJOM (osiguranje od tihog raspada kesa)
  - rucno: python scrape_halo_two_step.py --mode prodaja --full

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
    # Halo koristi "5+" za petosoban i vise
    "5+": "5.0", "6+": "5.0", "6.0": "5.0",
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


def get_listing_urls(mode: str, max_pages: int = 100) -> tuple[list[str], dict, dict, int]:
    """Korak 1: skupi sve URL-ove oglasa sa listing stranica.
    Vraća (lista URL-ova, ag_map: url->agencija_slug, price_map: url->cena, broj requestova).
    Agencija slug i cena se čitaju sa kartice dok smo na listing stranici —
    cena služi za dnevno osvežavanje keširanih oglasa bez Koraka 2.
    """
    all_urls = []
    ag_map = {}
    price_map = {}
    seen = set()
    requests_count = 0
    base = BASE_URLS[mode]

    for page_num in range(1, max_pages + 1):
        url = base if page_num == 1 else f"{base}?page={page_num}"
        print(f"  Listing str. {page_num}: {url}", flush=True)

        try:
            resp = scraper_get(url)
            requests_count += 1
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

            # Cena sa kartice (data-value) — za dnevno osvezavanje kesa
            price_el = card.select_one("span[data-value]")
            if price_el:
                try:
                    pv = float(str(price_el.get("data-value", "")).replace(",", "."))
                    if pv > 100:
                        price_map[full_url] = pv
                except Exception:
                    pass

            # Agencija slug sa kartice — /oglasi/NAZIV href
            for a in card.find_all("a", href=re.compile(r"/oglasi/", re.I)):
                m = re.search(r"/oglasi/([^/?#]+)", a.get("href", ""), re.I)
                if m:
                    slug = m.group(1).strip()
                    if 2 < len(slug) < 80:
                        ag_map[full_url] = slug
                        break

        print(f"    -> {new_count} novih URL-ova (ukupno: {len(all_urls)}, kartica na str: {len(cards)})")

        if len(cards) == 0:
            print("  Nema vise kartica, stajem.")
            break

        time.sleep(0.3)

    return all_urls, ag_map, price_map, requests_count


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


def scrape_oglas(url: str, ag_from_card: str | None = None) -> dict | None:
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

    # Fallback: veliki stanovi bez podatka o sobama -> 5.0 (Petosoban+)
    # Isto kao u NRS scraperu — agencije cesto ne popune broj soba za
    # luksuzne stanove; na Novom Beogradu 130+ m² je pouzdano petosoban+.
    if struktura == "ostalo" and m2 and m2 >= 130:
        struktura = "5.0"

    cena_m2 = round(cena / m2) if cena and m2 and m2 > 5 else None

    # Agencija — slug izvučen sa listing kartice u Koraku 1
    soup = BeautifulSoup(html, "html.parser")
    agencija = ag_from_card or None
    oglasivac_tip = other.get("oglasivac_nekretnine_s", "")
    # Ako je privatno lice, poništi agenciju
    if oglasivac_tip and oglasivac_tip.lower() not in ("agencija", ""):
        agencija = None

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


CACHE_TTL_DAYS = 30

def load_cache(mode: str) -> dict:
    """Kes presuda po oglasu: id -> {url, verdikt, listing|None, last_seen, scraped_at}.
    verdikt: "relevantan" (u nasih 18 zgrada) ili "nerelevantan"."""
    f = DATA / f"cache_halo_{mode}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            print("  UPOZORENJE: kes nije citljiv, gradim ispocetka.")
    return {}


def save_cache(mode: str, cache: dict):
    danas = date.today()
    ziv = {}
    for k, v in cache.items():
        try:
            starost = (danas - date.fromisoformat(v.get("last_seen", str(danas)))).days
        except Exception:
            starost = 0
        if starost <= CACHE_TTL_DAYS:
            ziv[k] = v
    (DATA / f"cache_halo_{mode}.json").write_text(
        json.dumps(ziv, ensure_ascii=False), encoding="utf-8")
    return len(cache) - len(ziv)


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
    parser.add_argument("--max-pages", type=int, default=100)
    parser.add_argument("--full", action="store_true",
                        help="Full refresh: ignorisi kes, scrape-uj sve oglase iznova")
    args = parser.parse_args()
    mode = args.mode

    full_refresh = args.full or date.today().weekday() == 6  # nedelja = auto full
    danas = str(date.today())

    if not SCRAPER_API_KEY:
        print("ERROR: SCRAPER_API_KEY nije postavljen.")
        sys.exit(1)

    latest_file = DATA / f"latest_halo_{mode}.json"
    prev_ids = set()
    if latest_file.exists():
        prev = json.loads(latest_file.read_text(encoding="utf-8"))
        prev_ids = {l["id"] for l in prev.get("listings", [])}

    rezim = "FULL REFRESH" + (" (nedelja)" if not args.full and full_refresh else "") if full_refresh else "inkrementalni"
    print(f"\n=== NB Tracker - Halo Oglasi [dva koraka, {rezim}] [{mode}] ===")

    print(f"\n[Korak 1] Skupljam URL-ove oglasa...")
    all_urls, ag_map, price_map, k1_requests = get_listing_urls(mode, args.max_pages)
    print(f"\nUkupno URL-ova: {len(all_urls)} | Agencija pronađeno: {len(ag_map)}")

    # ── Kes: poznate oglase citamo iz kesa, samo nove scrape-ujemo ──
    cache = {} if full_refresh else load_cache(mode)
    all_raw = []
    to_scrape = []
    iz_kesa_rel = 0
    iz_kesa_nerel = 0
    cena_azurirana = 0

    for url in all_urls:
        lid = normalize_id(url)
        c = cache.get(lid)
        if c is None:
            to_scrape.append(url)
            continue
        c["last_seen"] = danas
        if c.get("verdikt") == "relevantan" and c.get("listing"):
            l = dict(c["listing"])
            nova_cena = price_map.get(url)
            if nova_cena and nova_cena != l.get("cena"):
                l["cena"] = nova_cena
                if l.get("m2") and l["m2"] > 5:
                    l["cena_m2"] = round(nova_cena / l["m2"])
                c["listing"] = l
                cena_azurirana += 1
            all_raw.append(l)
            iz_kesa_rel += 1
        else:
            iz_kesa_nerel += 1

    print(f"[KES] Poznato: {iz_kesa_rel + iz_kesa_nerel} "
          f"(relevantnih {iz_kesa_rel}, cena osvezeno {cena_azurirana}) | "
          f"Novo za scrape: {len(to_scrape)}")

    print(f"\n[Korak 2] Scrape-ujem {len(to_scrape)} oglasa paralelno (8 threadova)...")
    completed = 0
    lock = __import__("threading").Lock()

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def scrape_with_progress(url):
        nonlocal completed
        result = scrape_oglas(url, ag_map.get(url))
        with lock:
            completed += 1
            if completed % 20 == 0:
                print(f"  {completed}/{len(to_scrape)} oglasa ({len(all_raw)} relevantnih)...", flush=True)
        return result

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(scrape_with_progress, url): url for url in to_scrape}
        for future in as_completed(futures):
            url = futures[future]
            listing = None
            try:
                listing = future.result()
            except Exception:
                pass
            with lock:
                cache[normalize_id(url)] = {
                    "url": url,
                    "verdikt": "relevantan" if listing else "nerelevantan",
                    "listing": listing,
                    "last_seen": danas,
                    "scraped_at": danas,
                }
                if listing:
                    all_raw.append(listing)

    unique = compute_dedup(all_raw)
    curr_ids = {l["id"] for l in unique}

    # ── Zastita od loseg run-a (potroseni ScraperAPI krediti, blokade...) ──
    # Ako je novi rezultat drasticno manji od postojecih podataka, NE gazi ih.
    # Zivi u scraperu (ne u bat-u) da vazi za SVAKI nacin pokretanja.
    if latest_file.exists():
        try:
            prev_cnt = len(json.loads(latest_file.read_text(encoding="utf-8")).get("listings", []))
        except Exception:
            prev_cnt = 0
        if prev_cnt >= 20 and len(unique) < prev_cnt * 0.5:
            print(f"\nSTOP: novi rezultat ({len(unique)} oglasa) je manji od 50% "
                  f"prethodnog ({prev_cnt}). Sumnja na los scrape — fajlovi NISU pisani.")
            sys.exit(2)

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

    ociscen = save_cache(mode, cache)
    ukupno_req = k1_requests + len(to_scrape)
    print(f"[KES] Sacuvano {len(cache) - ociscen} presuda"
          + (f" (ociscen {ociscen} starijih od {CACHE_TTL_DAYS} dana)" if ociscen else ""))
    print(f"[POTROSNJA] Korak 1: {k1_requests} req | Korak 2: {len(to_scrape)} req | "
          f"Ukupno: {ukupno_req} req (~{ukupno_req * 10} kredita)")


if __name__ == "__main__":
    main()
