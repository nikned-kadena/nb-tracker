@echo off
cd /d C:\nb-tracker

echo ============================================
echo  NB Tracker Scrape [%date% %time%]
echo ============================================
echo.

echo [1/4] Halo Oglasi - Prodaja...
python scraper\scrape_halo_two_step.py --mode prodaja
if errorlevel 1 echo GRESKA: Halo prodaja

echo.
echo [2/4] Halo Oglasi - Renta...
python scraper\scrape_halo_two_step.py --mode renta
if errorlevel 1 echo GRESKA: Halo renta

echo.
echo [3/4] Nekretnine.rs - Prodaja...
python scraper\scrape_nrs_playwright.py --mode prodaja
if errorlevel 1 echo GRESKA: NRS prodaja

echo.
echo [4/4] Nekretnine.rs - Renta...
python scraper\scrape_nrs_playwright.py --mode renta
if errorlevel 1 echo GRESKA: NRS renta

echo.
echo Proveravam kvalitet scrape rezultata...
python -c "
import json, sys

thresholds = {
    'data/latest_halo_prodaja.json': 50,
    'data/latest_halo_renta.json':   50,
    'data/latest_nrs_prodaja.json':  30,
    'data/latest_nrs_renta.json':    30,
}

ok = True
for f, min_count in thresholds.items():
    try:
        d = json.load(open(f, encoding='utf-8'))
        count = d.get('total_unique', 0)
        if count < min_count:
            print(f'UPOZORENJE: {f} ima samo {count} oglasa (minimum: {min_count})')
            ok = False
        else:
            print(f'OK: {f} - {count} oglasa')
    except Exception as e:
        print(f'GRESKA pri citanju {f}: {e}')
        ok = False

if not ok:
    print('Scrape rezultati su sumnjivi - commit preskocen!')
    sys.exit(1)
print('Svi fajlovi validni - nastavljam sa commitom...')
"
if errorlevel 1 (
    echo.
    echo !! COMMIT PRESKOCEN zbog losih scrape rezultata !!
    echo ============================================
    echo  Gotovo sa greskom [%time%]
    echo ============================================
    exit /b 1
)

echo.
echo Commitujem podatke na GitHub...
git add data\
git diff --staged --quiet && echo "Nema promena u podacima." && goto :end

git commit -m "data: automatski scrape %date%"
git pull --rebase -X ours origin main
git push origin main
echo Push uspesno.

:end
echo.
echo ============================================
echo  Gotovo [%time%]
echo ============================================