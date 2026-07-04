@echo off
REM ============================================================
REM NB Tracker Scrape - run_nrs.bat v2 (04.07.2026)
REM Izmene u odnosu na v1 (lekcije iz BnV sesije 04.07):
REM   1. PYTHONUTF8=1 - srpska slova u printovima ne obaraju scrapere
REM   2. GIT_MERGE_AUTOEDIT=no - merge poruke prolaze bez Vim-a
REM   3. git pull --no-rebase umesto --rebase (CRLF fantom obarao rebase)
REM   4. Prava provera errorlevel-a posle git push (nema laznog [OK])
REM   5. Brana svezine: sva 4 latest_*.json moraju biti od DANAS
REM   6. Stanje ScraperAPI kredita se upisuje u log posle svakog run-a
REM Lokacija: C:\nb-tracker\scraper\run_nrs.bat
REM ============================================================
setlocal enabledelayedexpansion
set PYTHONUTF8=1
set GIT_MERGE_AUTOEDIT=no
cd /d C:\nb-tracker

set LOG=scraper\run.log
echo. >> %LOG%
echo ============================================ >> %LOG%
echo   NB Tracker Scrape v2  %date% %time% >> %LOG%
echo ============================================ >> %LOG%

echo ============================================
echo   NB Tracker Scrape v2  %date% %time%
echo ============================================

REM -- Povuci najnoviju verziju koda PRE scrape-a (merge, ne rebase) --
echo [PULL] Povlacim najnoviju verziju koda... >> %LOG%
git pull --no-rebase --no-edit -X ours origin main >> %LOG% 2>&1

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

REM -- KLJUCNA BRANA 1: ako je BILO KOJI scraper pao, NE diramo git --
if "%FAIL%"=="1" (
    echo.
    echo !! BAR JEDAN SCRAPER NIJE USPEO - GIT SE NE DIRA, PODACI OSTAJU NETAKNUTI !!
    echo !! Detalji u scraper\run.log !!
    echo.
    echo [ABORT] Bar jedan scraper pao - commit preskocen, podaci netaknuti. >> %LOG%
    goto :krediti_greska
)

REM -- KLJUCNA BRANA 2: svi latest_*.json moraju biti modifikovani DANAS --
REM -- (BnV lekcija: scraper moze "uspeti" a ne upisati nista novo) --
python -c "import os,sys,datetime; danas=datetime.date.today(); fajlovi=['data/latest_halo_prodaja.json','data/latest_halo_renta.json','data/latest_nrs_prodaja.json','data/latest_nrs_renta.json']; stari=[f for f in fajlovi if not os.path.exists(f) or datetime.date.fromtimestamp(os.path.getmtime(f))!=danas]; print('[BRANA] Svi fajlovi svezi ('+str(danas)+')' if not stari else '[BRANA] NISU svezi: '+', '.join(stari)); sys.exit(1 if stari else 0)" >> %LOG% 2>&1
if errorlevel 1 (
    echo.
    echo !! PODACI NISU SVEZI - commit preskocen, detalji u run.log !!
    echo [ABORT] Podaci nisu od danas - commit preskocen. >> %LOG%
    goto :krediti_greska
)

REM -- Svi scraperi uspeli i podaci svezi - bezbedno je commitovati --
echo.
echo Svi scraperi uspesni. Commitujem na GitHub...
echo [COMMIT] Svi scraperi uspeli, commitujem... >> %LOG%
git add data\
git diff --cached --quiet && ( echo    Nema promena u podacima. & echo [SKIP] Nema promena. >> %LOG% & goto :petak )

git commit -m "data: automatski scrape %date%" >> %LOG% 2>&1
git pull --no-rebase --no-edit -X ours origin main >> %LOG% 2>&1
git push origin main >> %LOG% 2>&1
if errorlevel 1 (
    echo    ^>^> PUSH NEUSPESAN - podaci ostaju lokalno!
    echo [GRESKA] Push NEUSPESAN - commit postoji lokalno, resiti rucno. >> %LOG%
    goto :krediti_greska
)
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

REM -- Stanje ScraperAPI kredita u log (besplatan /account endpoint) --
python -c "import os,requests; d=requests.get('http://api.scraperapi.com/account',params={'api_key':os.environ.get('SCRAPER_API_KEY','')},timeout=30).json(); print('[KREDITI] '+str(d.get('requestCount'))+' od '+str(d.get('requestLimit'))+' iskorisceno')" >> %LOG% 2>&1

echo.
echo ============================================
echo   Gotovo  %time%
echo ============================================
echo ============================================ >> %LOG%
echo   Zavrseno OK  %time% >> %LOG%
echo ============================================ >> %LOG%
endlocal
exit /b 0

:krediti_greska
REM -- I u slucaju greske zabelezi stanje kredita, pa izadji sa 1 --
python -c "import os,requests; d=requests.get('http://api.scraperapi.com/account',params={'api_key':os.environ.get('SCRAPER_API_KEY','')},timeout=30).json(); print('[KREDITI] '+str(d.get('requestCount'))+' od '+str(d.get('requestLimit'))+' iskorisceno')" >> %LOG% 2>&1
echo ============================================ >> %LOG%
echo   Zavrseno SA GRESKOM  %time% >> %LOG%
echo ============================================ >> %LOG%
endlocal
exit /b 1
