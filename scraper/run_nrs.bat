@echo off
cd /d C:\nb-tracker

echo ============================================
echo  NB Tracker Scrape [%date% %time%]
echo ============================================
echo.

REM SCRAPER_API_KEY mora biti postavljen trajno preko setx
REM (jednom uradi: setx SCRAPER_API_KEY "tvoj_kljuc")

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