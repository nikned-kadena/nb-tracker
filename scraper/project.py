#!/usr/bin/env python3
"""
project.py — projektuje registar u fajlove koje dashboard ume da cita.

ZASTO POSTOJI
-------------
Dashboard ucitava `latest_{izvor}_{mod}.json` i `history_{izvor}_{mod}.json`.
Tako je bilo dok su postojala samo dva izvora i svaki je pisao svoj fajl.

Novi izvori (4zida, Nadji Dom) NE pisu takve fajlove — oni pune registar,
gde se isti stan sa vise portala spaja u JEDAN zapis. To je i poenta: ne
zelimo cetiri odvojena prikaza istog trzista.

Ovaj skript zato iz registra pravi:

  latest_4zida_{mod}.json      samo oglasi vidjeni na 4zida
  latest_nadjidom_{mod}.json   samo oglasi vidjeni na Nadji Dom
  latest_all_{mod}.json        SVI aktivni, spojeni — glavni prikaz
  history_*_{mod}.json         dnevna serija rekonstruisana iz registra

`latest_halo_{mod}.json` se NE dira — njega i dalje pise Halo scraper i on
ostaje merodavan za Halo prikaz.

REKONSTRUISANA ISTORIJA
-----------------------
Za "all" prikaz nema nasledjene istorije, ali registar je moze dati: za svaki
dan se broji koliko je oglasa tog dana bilo aktivno (first_seen <= dan <=
deactivated_at). To je stvarna dnevna serija, ne procena — i ide unazad do
pocetka pracenja.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

IZVORI = ["4zida", "nadjidom"]


def _listing(e: dict) -> dict:
    """Zapis iz registra -> oblik koji dashboard ocekuje u `listings`."""
    return {
        "id": e.get("uid"),
        "url": (e.get("source_urls") or [None])[0],
        "naslov": e.get("naslov"),
        "zgrada": e.get("zgrada"),
        "agencija": e.get("agencija"),
        "struktura": e.get("struktura"),
        "str_label": e.get("str_label"),
        "m2": e.get("m2"),
        "cena": e.get("price_current"),
        "cena_m2": (round(e["price_current"] / e["m2"])
                    if e.get("price_current") and e.get("m2") else None),
        "sprat": e.get("sprat"),
        # dodatna polja koja stari fajlovi nemaju — dashboard ih ignorise,
        # ali su tu za buduce prikaze
        "izvori": e.get("sources"),
        "dana_na_trzistu": e.get("days_listed"),
        "prva_cena": e.get("price_first"),
        "promena_cene_pct": (round(100 * (e["price_current"] - e["price_first"])
                                   / e["price_first"], 1)
                             if e.get("price_first") and e.get("price_current")
                             and e["price_first"] != e["price_current"] else None),
        "first_seen": e.get("first_seen"),
        "last_seen": e.get("last_seen"),
    }


def _istorija(entries: list, mode: str) -> list:
    """Dnevni broj aktivnih oglasa, rekonstruisan iz registra."""
    if not entries:
        return []
    danas = date.today()
    poc = min(date.fromisoformat(e["first_seen"]) for e in entries)
    raspon = []
    d = poc
    while d <= danas:
        raspon.append(d)
        d += timedelta(days=1)
    if len(raspon) > 400:           # ne pravi seriju duzu od ~13 meseci
        raspon = raspon[-400:]

    out = []
    for d in raspon:
        ds = d.isoformat()
        zivi = [e for e in entries
                if e["first_seen"] <= ds
                and (e.get("deactivated_at") is None or e["deactivated_at"] > ds)]
        if not zivi:
            continue
        cene = [e["price_current"] for e in zivi if e.get("price_current")]
        m2s = [e["m2"] for e in zivi if e.get("m2")]
        novi = sum(1 for e in zivi if e["first_seen"] == ds)
        skinuti = sum(1 for e in entries if e.get("deactivated_at") == ds)
        out.append({
            "date": ds,
            "mode": mode,
            "count": len(zivi),
            "total_raw": len(zivi),
            "total_unique": len(zivi),
            "total_dups": 0,
            "diff_new": novi,
            "diff_removed": skinuti,
            "avg_cena": round(sum(cene) / len(cene)) if cene else None,
            "avg_m2": round(sum(m2s) / len(m2s), 1) if m2s else None,
        })
    # Odseci pocetne dane sa besmisleno malim brojem oglasa.
    # Najstarije verzije latest_*.json u git-u imaju drugaciju semu (polje
    # `cena` je tamo EUR/m2), pa backfill iz njih izvuce samo sacicu zapisa.
    # Serija koja pocinje sa 5 oglasa pa skoci na 150 nije trzisni trend nego
    # artefakt — i na grafiku bi izgledala kao eksplozija ponude.
    if out:
        med = sorted(x["count"] for x in out)[len(out)//2]
        prag = max(1, int(med * 0.3))
        prvi_validan = next((i for i, x in enumerate(out) if x["count"] >= prag), 0)
        if prvi_validan:
            print(f"  [PROJ] odseceno {prvi_validan} pocetnih dana "
                  f"(ispod {prag} oglasa — nepouzdana stara sema)")
            out = out[prvi_validan:]
    return out


def _upisi(data_dir: Path, ime: str, entries: list, mode: str):
    aktivni = [e for e in entries if e.get("is_active")]
    listings = [_listing(e) for e in aktivni]
    danas = date.today().isoformat()

    payload = {
        "mode": mode,
        "source": ime,
        "date": danas,
        "scraped_at": danas,
        "total_raw": len(listings),
        "total_unique": len(listings),
        "total_dups": 0,
        "diff_new": [l["id"] for l in listings if l.get("first_seen") == danas],
        "diff_removed": [e.get("uid") for e in entries
                         if e.get("deactivated_at") == danas],
        "listings": listings,
    }
    (data_dir / f"latest_{ime}_{mode}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (data_dir / f"history_{ime}_{mode}.json").write_text(
        json.dumps(_istorija(entries, mode), ensure_ascii=False, indent=2),
        encoding="utf-8")
    return len(listings)


def build(data_dir: Path, mode: str):
    p = data_dir / f"registry_{mode}.json"
    if not p.exists():
        print(f"  [PROJ] Nema {p.name} — preskacem.", file=sys.stderr)
        return

    entries = list(json.loads(p.read_text(encoding="utf-8")).get("entries", {}).values())
    if not entries:
        print(f"  [PROJ] Registar {mode} je prazan.", file=sys.stderr)
        return

    n_all = _upisi(data_dir, "all", entries, mode)
    red = [f"all: {n_all}"]
    for izv in IZVORI:
        sub = [e for e in entries if izv in (e.get("sources") or [])]
        if sub:
            red.append(f"{izv}: {_upisi(data_dir, izv, sub, mode)}")
        else:
            red.append(f"{izv}: 0 (preskocen)")
    print(f"  [PROJ] {mode} → " + " | ".join(red))


if __name__ == "__main__":
    dd = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "data"
    for m in ("prodaja", "renta"):
        build(dd, m)
