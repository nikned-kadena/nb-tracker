@echo off
REM NB Tracker — lokalni scraper (Halo Oglasi + Nekretnine.rs)
REM Task Scheduler: pokrenuti svaki dan u 07:30

cd /d %~dp0..

echo ============================================
echo  NB Tracker Scrape [%date% %time%]
echo ============================================
echo.

echo [1/4] Halo Oglasi - Prodaja...
python scraper\scrape_halo_playwright.py --mode prodaja
if errorlevel 1 echo GRESKA: Halo prodaja

echo.
echo [2/4] Halo Oglasi - Renta...
python scraper\scrape_halo_playwright.py --mode renta
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
echo Commitujem podatke na GitHub...
git add data\
git diff --staged --quiet && echo "Nema promena u podacima." && goto :end

git commit -m "data: scrape %date%"
git pull --rebase -X ours origin main
git push origin main
echo Push uspesno.

:end
echo.
echo ============================================
echo  Gotovo [%time%]
echo ============================================
