@echo off
REM NB Tracker — lokalni NRS scraper (pokrenuti na desktopu)
REM Task Scheduler: podesiti na 07:30 svaki dan

cd /d %~dp0..

echo === NB Tracker NRS Scrape [%date% %time%] ===
echo.

echo [1/2] Prodaja...
python scraper\scrape_nrs_playwright.py --mode prodaja
if errorlevel 1 echo GRESKA u prodaji scrape-u

echo.
echo [2/2] Renta...
python scraper\scrape_nrs_playwright.py --mode renta
if errorlevel 1 echo GRESKA u renta scrape-u

echo.
echo Commitujem podatke...
git add data\
git diff --staged --quiet && echo "Nema promena." && goto :end

git commit -m "data: nrs scrape %date%"
git pull --rebase -X ours origin main
git push origin main

:end
echo.
echo === Gotovo ===
