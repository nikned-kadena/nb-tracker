# NB Tracker 🏙️

**Market intelligence dashboard za praćenje oglasa na Novom Beogradu.**

Prati 7 projekata: **Wellport · West 65 · Soul 64 · Airport Garden · Zepterra · New Minel · A Blok**

Dashboard: `https://niknedeljko.github.io/nb-tracker`

---

## Arhitektura

```
nb-tracker/
├── scraper/
│   ├── buildings.py              # Ključne reči za detekciju zgrada
│   ├── scrape_halo.py            # Halo Oglasi scraper (ScraperAPI)
│   ├── scrape_nrs_playwright.py  # Nekretnine.rs scraper (Playwright, lokalni)
│   ├── run_nrs.bat               # Windows batch za Task Scheduler
│   └── requirements.txt
├── data/
│   ├── latest_halo_prodaja.json  # Poslednji Halo Oglasi prodaja snapshot
│   ├── latest_halo_renta.json    # Poslednji Halo Oglasi renta snapshot
│   ├── latest_nrs_prodaja.json   # Poslednji NRS prodaja snapshot
│   ├── latest_nrs_renta.json     # Poslednji NRS renta snapshot
│   ├── history_halo_prodaja.json # Dnevna istorija Halo prodaja
│   ├── history_halo_renta.json   # Dnevna istorija Halo renta
│   ├── history_nrs_prodaja.json  # Dnevna istorija NRS prodaja
│   └── history_nrs_renta.json    # Dnevna istorija NRS renta
├── dashboard/
│   └── src/Dashboard.jsx         # React dashboard
└── .github/workflows/
    ├── daily_scrape.yml          # Halo Oglasi — GitHub Actions (08:00 UTC)
    └── deploy.yml                # Deploy dashboard na GitHub Pages
```

---

## Setup (prvi put)

### 1. Napravi GitHub repo

Kreiraj novi repo: `niknedeljko/nb-tracker`

### 2. GitHub Secrets

`Settings → Secrets and variables → Actions → New repository secret`

| Ime | Vrednost |
|-----|----------|
| `SCRAPER_API_KEY` | tvoj ScraperAPI ključ |

### 3. GitHub Pages

`Settings → Pages → Source → Deploy from branch: gh-pages`

### 4. Actions permisije

`Settings → Actions → General → Workflow permissions → Read and write`

### 5. Lokalni setup (za NRS scraper na desktopu)

```bash
pip install playwright beautifulsoup4
playwright install chromium
```

Klonuj repo:
```bash
git clone https://github.com/niknedeljko/nb-tracker.git
cd nb-tracker
```

### 6. Task Scheduler (Windows)

- Program: `C:\putanja\do\nb-tracker\scraper\run_nrs.bat`
- Pokretanje: svaki dan u 07:30
- ✅ Run whether user is logged on or not
- ✅ Wake the computer to run this task

---

## Fajl konvencije

| Fajl | Izvor | Sadržaj |
|------|-------|---------|
| `latest_halo_prodaja.json` | Halo Oglasi | Aktuelni prodaja snapshot |
| `latest_halo_renta.json` | Halo Oglasi | Aktuelni renta snapshot |
| `latest_nrs_prodaja.json` | Nekretnine.rs | Aktuelni prodaja snapshot |
| `latest_nrs_renta.json` | Nekretnine.rs | Aktuelni renta snapshot |

---

## Zgrade i ključne reči

| Projekat | Ključne reči |
|----------|-------------|
| Airport Garden | `airport garden` |
| New Minel | `new minel`, `newminel` |
| Soul 64 | `soul 64`, `soul64`, `soul` |
| Wellport | `wellport` |
| West 65 | `west 65`, `west65` |
| Zepterra | `zepterra` |
| A Blok | `a blok faza`, `a-blok`, `a blok` |
