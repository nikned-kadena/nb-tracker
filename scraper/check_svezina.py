"""
check_svezina.py - Brana svezine za NB Tracker.

v2 (28.08.2026): NRS fajlovi izbaceni iz brane zbog DataDome blokade.
Prethodna verzija je zahtevala sva 4 fajla (halo + nrs) da budu svezi
DANAS. Kad je Nekretnine.rs 13.07.2026 uveo DataDome anti-bot, NRS scrape
je pocho da vraca 0 URL-ova - STOP guard je pravilno preskocio pisanje,
ali brana je onda abortovala commit i ZDRAVIH Halo podataka.
Rezultat: dashboard nije azuriran skoro mesec dana iako Halo scraper radi.

Sada brana proverava samo Halo fajlove. NRS fajlovi ostaju zamrznuti dok
ne odlucimo o DataDome bypass-u.

Zivi kao zaseban fajl (ne kao python -c u bat-u) jer cmd delayed
expansion unistava '!' karaktere u inline komandama (naucena lekcija 06.07.2026).
Exit 0 = svezi, exit 1 = nisu.
"""
import os
import sys
import datetime

danas = datetime.date.today()

# Samo Halo fajlovi - NRS je zamrznut dok se DataDome ne resi
fajlovi = [
    "data/latest_halo_prodaja.json",
    "data/latest_halo_renta.json",
]

stari = [
    f for f in fajlovi
    if not (os.path.exists(f) and datetime.date.fromtimestamp(os.path.getmtime(f)) == danas)
]

if stari:
    print("[BRANA] NISU svezi: " + ", ".join(stari))
    sys.exit(1)

print("[BRANA] Svi Halo fajlovi svezi (" + str(danas) + ")")
sys.exit(0)