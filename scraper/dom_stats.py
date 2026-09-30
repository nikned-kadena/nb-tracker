#!/usr/bin/env python3
"""
dom_stats.py — statistika trajanja oglasa (days on market).

Cita `registry_{mode}.json` i pravi `dom_{mode}.json` za dashboard.

STATISTICKO UPOZORENJE — procitaj pre nego sto brojeve staviš u izveštaj
-----------------------------------------------------------------------
Postoje DVE razlicite velicine i mesanje te dve je najcesca greska u ovoj
vrsti analize:

  ZAVRSENI oglasi  — stan je skinut, znamo koliko je stvarno stajao.
                     Ovo je prava mera "koliko treba da se proda".

  AKTIVNI oglasi   — stan je jos u ponudi, znamo samo koliko VEC stoji.
                     Ovo je starost, ne trajanje. Uvek je manja od konacnog
                     broja, jer se meri na pola puta.

Medijana svih zajedno nema smisla. Zato ih ovde racunamo odvojeno i nikad
ih ne sabiramo. U izvestaju se citira ZAVRSENI broj, uz napomenu koliko je
uzoraka iza njega.

Jos jedno ogranicenje: oglas koji je bio na trzistu PRE nego sto je registar
napravljen ima `first_seen` = dan pocetka pracenja, ne stvarni dan objave.
Zato `backfill_registry.py` prvo prosece sve stare snapshot fajlove — bez
toga su svi brojevi prvih nedelja podcenjeni.
"""

import json
import sys
from datetime import date
from pathlib import Path
from statistics import median


MIN_UZORAK = 5  # ispod ovoga se medijana ne prikazuje, prikazuje se n


def _med(v):
    return round(median(v)) if v else None


def _grupa(zapisi, today):
    zavrseni = [e for e in zapisi if not e.get("is_active") and e.get("deactivated_at")]
    aktivni = [e for e in zapisi if e.get("is_active")]

    d_zav = [e["days_listed"] for e in zavrseni if e.get("days_listed") is not None]
    d_akt = [e["days_listed"] for e in aktivni if e.get("days_listed") is not None]

    out = {
        "n_zavrseni": len(d_zav),
        "n_aktivni": len(d_akt),
        "dom_medijana": _med(d_zav) if len(d_zav) >= MIN_UZORAK else None,
        "dom_prosek": round(sum(d_zav) / len(d_zav)) if d_zav else None,
        "starost_aktivnih_medijana": _med(d_akt) if len(d_akt) >= MIN_UZORAK else None,
        "pouzdano": len(d_zav) >= MIN_UZORAK,
    }
    if d_zav:
        s = sorted(d_zav)
        out["dom_p25"] = s[len(s) // 4]
        out["dom_p75"] = s[(3 * len(s)) // 4]
        out["brzo_do_30d"] = round(100 * sum(1 for x in d_zav if x <= 30) / len(d_zav))
        out["sporo_preko_180d"] = round(100 * sum(1 for x in d_zav if x > 180) / len(d_zav))
    return out


def build(data_dir: Path, mode: str) -> dict:
    p = data_dir / f"registry_{mode}.json"
    if not p.exists():
        print(f"  [DOM] Nema {p.name} — preskacem.", file=sys.stderr)
        return {}

    reg = json.loads(p.read_text(encoding="utf-8"))
    zapisi = list(reg.get("entries", {}).values())
    today = date.today().isoformat()

    po_zgradi, po_strukturi = {}, {}
    for e in zapisi:
        po_zgradi.setdefault(e.get("zgrada") or "neidentifikovano", []).append(e)
        po_strukturi.setdefault(e.get("str_label") or "nepoznato", []).append(e)

    # cena vs brzina: da li jeftiniji stanovi brze odlaze
    zav = [e for e in zapisi if not e.get("is_active") and e.get("days_listed") is not None
           and e.get("price_first")]
    cena_vs_dom = []
    if len(zav) >= 20:
        zav.sort(key=lambda e: e["price_first"])
        k = max(len(zav) // 4, 1)
        for i, naziv in enumerate(["najjeftiniji 25%", "25-50%", "50-75%", "najskuplji 25%"]):
            deo = zav[i * k:(i + 1) * k] if i < 3 else zav[3 * k:]
            if deo:
                cena_vs_dom.append({
                    "kvartil": naziv,
                    "n": len(deo),
                    "cena_medijana": _med([e["price_first"] for e in deo]),
                    "dom_medijana": _med([e["days_listed"] for e in deo]),
                })

    # snizenja cene
    sa_promenom = [e for e in zapisi if e.get("price_changes")]
    snizenja = [c for e in sa_promenom for c in e["price_changes"] if c["to"] < c["from"]]

    out = {
        "mode": mode,
        "generated": today,
        "pocetak_pracenja": min((e["first_seen"] for e in zapisi), default=None),
        "ukupno": _grupa(zapisi, today),
        "po_zgradi": {k: _grupa(v, today) for k, v in sorted(po_zgradi.items())},
        "po_strukturi": {k: _grupa(v, today) for k, v in sorted(po_strukturi.items())},
        "cena_vs_dom": cena_vs_dom,
        "cene": {
            "oglasa_sa_promenom": len(sa_promenom),
            "ukupno_snizenja": len(snizenja),
            "prosecno_snizenje_pct": round(
                100 * sum((c["from"] - c["to"]) / c["from"] for c in snizenja) / len(snizenja), 1
            ) if snizenja else None,
        },
        "izvori": {},
        "napomena": (
            "dom_medijana se racuna SAMO na skinutim oglasima (zavrseno trajanje). "
            "starost_aktivnih_medijana je koliko vec stoje oglasi koji su jos u ponudi "
            "i sistematski je manja — te dve velicine se nikad ne sabiraju. "
            f"Medijana se prikazuje tek od {MIN_UZORAK} zavrsenih oglasa."
        ),
    }

    for e in zapisi:
        for s in e.get("sources", []):
            out["izvori"][s] = out["izvori"].get(s, 0) + 1

    (data_dir / f"dom_{mode}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    u = out["ukupno"]
    print(f"  [DOM] {mode}: zavrsenih {u['n_zavrseni']}, aktivnih {u['n_aktivni']}, "
          f"medijana trajanja {u['dom_medijana'] or '—'} dana")
    return out


if __name__ == "__main__":
    dd = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "data"
    for m in ("prodaja", "renta"):
        build(dd, m)
