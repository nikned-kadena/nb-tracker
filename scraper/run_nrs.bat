@echo off
setlocal enabledelayedexpansion
cd /d C:\nb-tracker

set LOG=scraper\run.log
echo. >> %LOG%
echo ============================================ >> %LOG%
echo   NB Tracker Scrape  %date% %time% >> %LOG%
echo ============================================ >> %LOG%

echo ============================================
echo   NB Tracker Scrape  %date% %time%
echo ============================================

REM -- Povuci najnoviju verziju koda PRE scrape-a --
echo [PULL] Povlacim najnoviju verziju koda... >> %LOG%
git pull --rebase -X ours origin main >> %LOG% 2>&1

REM -- Pokreni sva 4 scrapera. Svaki ima ugradjenu min-count zastitu --
REM -- (exit 2 = STOP, los scrape; exit 1 = greska). Belezimo svaki ishod. --
set FAIL=0

echo [1/4] Halo Oglasi - Prodaja...
echo [1/4] Halo Oglasi - Prodaja... >> %LOG%
python scraper\scrape_halo_two_step.py --mode prodaja >> %LOG% 2>&1
if errorlevel 1 ( echo    ^>^> NEUSPEH ^(exit !errorlevel!^) & echo    NEUSPEH Halo prodaja exit !errorlevel! >> %LOG% & set FAIL=1 )

echo [2/4] Halo Oglasi - Renta...
echo [2/4] Halo Oglasi - Renta... >> %LOG%
python scraper\scrape_halo_two_step.py --mode renta >> %LOG% 2>&1
if errorlevel 1 ( echo    ^>^> NEUSPEH ^(exit !errorlevel!^) & echo    NEUSPEH Halo renta exit !errorlevel! >> %LOG% & set FAIL=1 )

echo [3/4] Nekretnine.rs - Prodaja...
echo [3/4] Nekretnine.rs - Prodaja... >> %LOG%
python scraper\scrape_nrs_playwright.py --mode prodaja >> %LOG% 2>&1
if errorlevel 1 ( echo    ^>^> NEUSPEH ^(exit !errorlevel!^) & echo    NEUSPEH NRS prodaja exit !errorlevel! >> %LOG% & set FAIL=1 )

echo [4/4] Nekretnine.rs - Renta...
echo [4/4] Nekretnine.rs - Renta... >> %LOG%
python scraper\scrape_nrs_playwright.py --mode renta >> %LOG% 2>&1
if errorlevel 1 ( echo    ^>^> NEUSPEH ^(exit !errorlevel!^) & echo    NEUSPEH NRS renta exit !errorlevel! >> %LOG% & set FAIL=1 )

REM -- KLJUCNA BRANA: ako je BILO KOJI scraper pao, NE diramo git --
if "%FAIL%"=="1" (
    echo.
    echo !! BAR JEDAN SCRAPER NIJE USPEO - GIT SE NE DIRA, PODACI OSTAJU NETAKNUTI !!
    echo !! Detalji u scraper\run.log !!
    echo.
    echo [ABORT] Bar jedan scraper pao - commit preskocen, podaci netaknuti. >> %LOG%
    echo ============================================ >> %LOG%
    echo   Zavrseno SA GRESKOM  %time% >> %LOG%
    echo ============================================ >> %LOG%
    exit /b 1
)

REM -- Svi scraperi uspeli - bezbedno je commitovati --
echo.
echo Svi scraperi uspesni. Commitujem na GitHub...
echo [COMMIT] Svi scraperi uspeli, commitujem... >> %LOG%
git add data\
git diff --cached --quiet && ( echo    Nema promena u podacima. & echo [SKIP] Nema promena. >> %LOG% & goto :petak )

git commit -m "data: automatski scrape %date%" >> %LOG% 2>&1
git pull --rebase -X ours origin main >> %LOG% 2>&1
git push origin main >> %LOG% 2>&1
echo    Push uspesan.
echo [OK] Push uspesan. >> %LOG%

:petak
REM -- Petkom: nedeljni PDF izvestaj (posle scrape+push, bez novih kredita) --
for /f %%d in ('python -c "import datetime; print(datetime.date.today().weekday())"') do set DOW=%%d
if "%DOW%"=="4" (
    echo [PETAK] Generisem nedeljni PDF izvestaj... >> %LOG%
    echo Petak - generisem nedeljni PDF izvestaj...
    cd /d C:\nb-tracker\scraper
    python weekly_pdf_report.py >> run.log 2>&1
    cd /d C:\nb-tracker
)

echo.
echo ============================================
echo   Gotovo  %time%
echo ============================================
echo ============================================ >> %LOG%
echo   Zavrseno OK  %time% >> %LOG%
echo ============================================ >> %LOG%
endlocal