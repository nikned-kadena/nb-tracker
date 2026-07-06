"""
check_svezina.py — Brana svezine za NB Tracker.
Proverava da su sva 4 latest_*.json fajla modifikovana DANAS.
Zivi kao zaseban fajl (ne kao python -c u bat-u) jer cmd delayed
expansion unistava '!' karaktere u inline komandama (naucena lekcija 06.07.2026).
Exit 0 = svezi, exit 1 = nisu.
"""
import os
import sys
import datetime

danas = datetime.date.today()
fajlovi = [
    "data/latest_halo_prodaja.json",
    "data/latest_halo_renta.json",
    "data/latest_nrs_prodaja.json",
    "data/latest_nrs_renta.json",
]

stari = [
    f for f in fajlovi
    if not (os.path.exists(f) and datetime.date.fromtimestamp(os.path.getmtime(f)) == danas)
]

if stari:
    print("[BRANA] NISU svezi: " + ", ".join(stari))
    sys.exit(1)

print("[BRANA] Svi fajlovi svezi (" + str(danas) + ")")
sys.exit(0)