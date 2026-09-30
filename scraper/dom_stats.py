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


def kaplan_meier(zavrseni_dani, aktivni_dani):
    """Kaplan-Meier procena krive prezivljavanja i medijane trajanja.

    ZASTO OVO, A NE OBICNA MEDIJANA
    -------------------------------
    Izmereno na NB prodaji 30.09.2026: obicna medijana skinutih oglasa dala
    je 13 dana, Kaplan-Meier 29. Razlika nije sitnica nego faktor 2,2 — i
    obicna medijana je bila ona pogresna.

    Uzrok: od 484 oglasa, 162 su jos aktivna. To NISU nasumicnih 162, nego
    bas oni koji se najduze prodaju. Obicna medijana ih izbacuje i racuna
    samo one koji su stigli da se zatvore unutar prozora od tri meseca, pa
    sistematski potcenjuje trajanje. Ista greska kao kad bi prosecno trajanje
    braka merio anketirajuci samo razvedene.

    Kaplan-Meier aktivne oglase tretira kao CENZURISANA opazanja: ne zna se
    koliko ce ukupno trajati, ali se zna da su trajali bar toliko. Ta
    informacija ulazi u racun umesto da se baca.

    Vraca (medijana, kriva, udeo_prezivelih_na_kraju). Medijana je None ako
    kriva nikad ne padne ispod 50% — tada je prozor posmatranja prekratak da
    bi se medijana uopste videla, i to se mora reci umesto izmisliti broj.
    """
    obs = [(t, 1) for t in zavrseni_dani] + [(t, 0) for t in aktivni_dani]
    if not obs:
        return None, [], None
    obs.sort()

    n_riziku = len(obs)
    S = 1.0
    medijana = None
    kriva = []

    for t in sorted({t for t, _ in obs}):
        dogadjaja = sum(1 for tt, ev in obs if tt == t and ev == 1)
        cenzurisanih = sum(1 for tt, ev in obs if tt == t and ev == 0)
        if n_riziku <= 0:
            break
        if dogadjaja:
            S *= (1 - dogadjaja / n_riziku)
            kriva.append({"dan": t, "preziveli": round(S, 4)})
            if medijana is None and S <= 0.5:
                medijana = t
        n_riziku -= (dogadjaja + cenzurisanih)

    return medijana, kriva, round(S, 4)


def _grupa(zapisi, today):
    zavrseni = [e for e in zapisi if not e.get("is_active") and e.get("deactivated_at")]
    aktivni = [e for e in zapisi if e.get("is_active")]

    d_zav = [e["days_listed"] for e in zavrseni if e.get("days_listed") is not None]
    d_akt = [e["days_listed"] for e in aktivni if e.get("days_listed") is not None]

    km_med, km_kriva, S_kraj = kaplan_meier(d_zav, d_akt)
    dovoljno = (len(d_zav) + len(d_akt)) >= MIN_UZORAK

    out = {
        "n_zavrseni": len(d_zav),
        "n_aktivni": len(d_akt),

        # ── GLAVNI BROJ — ovaj se citira ──
        "dom_medijana": km_med if dovoljno else None,
        "metod": "kaplan-meier",
        "pouzdano": dovoljno and km_med is not None,

        # ── kontrolni brojevi, NE citirati kao trajanje ──
        "naivna_medijana_samo_skinuti": _med(d_zav) if d_zav else None,
        "starost_aktivnih_medijana": _med(d_akt) if d_akt else None,
        "udeo_jos_u_ponudi": S_kraj,
        "udeo_aktivnih_pct": round(100 * len(d_akt) / (len(d_zav) + len(d_akt))) if (d_zav or d_akt) else None,
    }

    if km_med is None and dovoljno:
        out["napomena_grupa"] = (
            "Kriva prezivljavanja nije pala ispod 50% u posmatranom prozoru — "
            "vise od polovine oglasa je jos u ponudi, pa se medijana jos ne moze "
            "izmeriti. Nije ista stvar kao 'nema podataka'.")

    if d_zav:
        s = sorted(d_zav)
        out["skinuti_p25"] = s[len(s) // 4]
        out["skinuti_p75"] = s[(3 * len(s)) // 4]
        out["brzo_do_30d"] = round(100 * sum(1 for x in d_zav if x <= 30) / len(d_zav))
        out["sporo_preko_180d"] = round(100 * sum(1 for x in d_zav if x > 180) / len(d_zav))
    if km_kriva:
        out["kriva"] = km_kriva[:: max(1, len(km_kriva) // 40)]  # do ~40 tacaka za graf
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
            "dom_medijana je Kaplan-Meier procena i JEDINI broj koji se citira kao "
            "trajanje oglasa. Aktivni oglasi ulaze u racun kao cenzurisana opazanja "
            "(trajali su BAR toliko), umesto da se izbace. "
            "naivna_medijana_samo_skinuti je kontrolni broj koji gleda samo zatvorene "
            "oglase i sistematski je POTCENJEN — na NB prodaji je davao 13 dana "
            "naspram stvarnih 29. Ne citirati ga. "
            "starost_aktivnih_medijana je koliko vec stoje oglasi koji su jos u "
            "ponudi; to je donja granica, ne trajanje. "
            f"Medijana se prikazuje tek od {MIN_UZORAK} oglasa u grupi."
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
