#!/usr/bin/env python3
"""
store.py — registar oglasa sa životnim ciklusom (BnV / NB Tracker).

ZASTO POSTOJI
-------------
Do sada je `latest_{mode}.json` bio fotografija DANASNJEG dana: oglas koji
se pojavi i nestane ne ostavlja trag osim broja u `diff_removed`. Zbog toga
nismo mogli da odgovorimo ni na jedno od ovih pitanja:

  - koliko dugo je stan bio na trzistu pre nego sto je skinut?
  - da li je isti stan objavljen i na Halo-u i na 4zida?
  - da li je cena menjana dok je stan stajao u ponudi?

Registar resava sva tri. On je JEDAN fajl po modu (`registry_{mode}.json`)
koji zivi preko svih run-ova i pamti svaki oglas koji smo ikada videli.

  latest_{mode}.json   -> ostaje NEPROMENJEN (dashboard ga i dalje cita)
  registry_{mode}.json -> novi, akumulativni sloj iznad njega

ZIVOTNI CIKLUS
--------------
  first_seen      prvi dan kad smo oglas videli
  last_seen       poslednji dan kad smo ga videli
  is_active       da li je bio u poslednjem uspesnom scrape-u
  deactivated_at  dan kad je progla�en skinutim (posle GRACE_DAYS)
  days_listed     trajanje oglasa u danima

GRACE PERIOD — zasto nije nula
------------------------------
Halo paginacija je nestabilna: 21.08. smo imali 157 renta oglasa, 12.09.
samo 114, 15.09. opet 119. Da smo deaktivirali sve sto nedostaje istog dana,
40 stanova bi bilo lazno "skinuto" pa "ponovo objavljeno" — i DOM statistika
bi bila smece. Zato oglas mora da nedostaje GRACE_DAYS uzastopnih run-ova
pre nego sto ga proglasimo skinutim.

ZASTITA OD LOSEG SCRAPE-A
-------------------------
Ako danasnji run donese manje od MIN_SEEN_RATIO aktivnih oglasa, deaktivacija
se NE izvrsava uopste. Ista filozofija kao STOP guard u scraper-u: radije
zastareli podaci nego pokvareni.
"""

import json
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

GRACE_DAYS = 2        # koliko uzastopnih dana oglas sme da nedostaje
MIN_SEEN_RATIO = 0.5  # ispod ovoga se deaktivacija preskace u celosti
PRICE_TOL = 0.05      # tolerancija cene za "loose" spajanje preko izvora


# ─────────────────────────────── otisci ────────────────────────────────

def _h(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def fingerprints(l: dict) -> tuple:
    """Vraca (fp_strict, fp_loose) za jedan oglas.

    Dva nivoa jer isti stan na dva portala retko ima identican naslov, ali
    skoro uvek ima istu zgradu, strukturu i kvadraturu.

      fp_strict = zgrada | struktura | m2 na jednu decimalu | cena
                  -> isti stan, ista cena. Spaja se bez pitanja.

      fp_loose  = zgrada | struktura | m2 zaokruzen | sprat
                  -> isti stan, cena se u medjuvremenu promenila.
                     Spaja se samo ako je cena u krugu od PRICE_TOL.

    Namerno NE koristi naslov ni agenciju: naslov pise agent i razlicit je
    na svakom portalu, a isti stan cesto oglasavaju dve agencije.
    """
    zgrada = (l.get("zgrada") or "").strip().lower()
    stru = l.get("struktura") or "?"
    m2 = l.get("m2") or 0
    cena = l.get("cena") or 0
    sprat = (l.get("sprat") or "?").strip().lower()

    fp_strict = _h("s", zgrada, stru, round(float(m2), 1), int(cena))
    fp_loose = _h("l", zgrada, stru, round(float(m2)), sprat)
    return fp_strict, fp_loose


def _price_close(a, b) -> bool:
    if not a or not b:
        return False
    return abs(a - b) <= max(a, b) * PRICE_TOL


# ────────────────────────── kapija ispravnosti ─────────────────────────

# Opsezi preuzeti iz parse_price() u scraper-u — isti pragovi, jedno mesto.
OPSEG_CENA = {"prodaja": (150_000, 5_000_000), "renta": (300, 50_000)}
OPSEG_M2 = (8, 600)


def validan(l: dict, mode: str) -> tuple:
    """Da li zapis sme da udje u registar. Vraca (ok, razlog).

    ZASTO POSTOJI — nalaz od 30.09.2026
    -----------------------------------
    Najstarija verzija latest_halo_prodaja.json u git istoriji ima DRUGACIJU
    semu: polje `cena` tamo drzi EUR/m2, ne prodajnu cenu. Backfill je te
    zapise uredno primio i u registru su se nasla 4 "stana od 2.422 EUR".
    Jedan od njih ima i pogresnu zgradu i kvadraturu 192 m2 dok mu naslov
    kaze 112 m2.

    Bez ove kapije, svaka promena seme na bilo kom portalu tiho zatruje
    registar — a registar je akumulativan, pa greska ostaje zauvek.
    Radije odbaci zapis nego da ga upises.
    """
    cena = l.get("cena")
    m2 = l.get("m2")
    lo, hi = OPSEG_CENA.get(mode, (0, 10**9))

    # granice UKLJUCIVE: penthouse od 443 m2 za tacno 5.000.000 EUR je
    # realan (11.270 EUR/m2), a padao bi na strogoj nejednakosti.
    if cena is not None and not (lo <= cena <= hi):
        return False, f"cena {cena} van opsega {lo}-{hi} za {mode}"
    if m2 is not None and not (OPSEG_M2[0] <= m2 <= OPSEG_M2[1]):
        return False, f"m2 {m2} van opsega {OPSEG_M2[0]}-{OPSEG_M2[1]}"
    if cena and m2:
        pm2 = cena / m2
        if mode == "prodaja" and not (1200 <= pm2 <= 25000):
            return False, f"cena/m2 {pm2:.0f} nerealna za prodaju"
        if mode == "renta" and not (3 <= pm2 <= 150):
            return False, f"cena/m2 {pm2:.1f} nerealna za rentu"
    return True, ""


# ─────────────────────────────── registar ──────────────────────────────

def load_registry(data_dir: Path, mode: str) -> dict:
    p = data_dir / f"registry_{mode}.json"
    if not p.exists():
        return {"schema_version": SCHEMA_VERSION, "mode": mode, "entries": {}}
    d = json.loads(p.read_text(encoding="utf-8"))
    d.setdefault("entries", {})
    return d


def save_registry(data_dir: Path, mode: str, reg: dict) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    p = data_dir / f"registry_{mode}.json"
    reg["schema_version"] = SCHEMA_VERSION
    reg["mode"] = mode
    reg["updated_at"] = datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _index(entries: dict) -> tuple:
    """Gradi indekse za brzo spajanje: po strict otisku i po loose otisku."""
    by_strict, by_loose = {}, {}
    for uid, e in entries.items():
        for fp in e.get("fp_strict_all", []):
            by_strict.setdefault(fp, uid)
        by_loose.setdefault(e.get("fp_loose"), []).append(uid)
    return by_strict, by_loose


def _match(l: dict, entries: dict, by_strict: dict, by_loose: dict,
           source: str, ext_id: str):
    """Nadji postojeci zapis za ovaj oglas, ili None.

    PRAVILO KOJE SPRECAVA NAJGORU GRESKU
    ------------------------------------
    U BW zgradama postoji mnogo stanova istog layouta: ista zgrada, ista
    struktura, ista kvadratura, isti sprat, cene u razmaku od par procenata.
    Loose otisak ih sve vidi kao jedan. Ako bismo spajali samo po otisku,
    pet razlicitih stanova bi postalo jedan zapis i DOM statistika bi bila
    besmislena.

    Zato je ID unutar portala merodavan:
      - isti portal, isti ID          -> sigurno isti oglas, spoji
      - isti portal, razlicit ID      -> po pravilu RAZLICIT stan.
                                         Spaja se samo na strogo podudaranje
                                         (zgrada+struktura+m2 na decimalu+cena
                                         u evro) UZ istu agenciju — to je
                                         dupla objava, ne dva stana.
      - drugi portal                  -> spoji na strict, ili na loose ako je
                                         cena u toleranciji.
    """
    fp_s, fp_l = fingerprints(l)

    # 1. isti portal, isti ID — najjaci signal, nema dvoumljenja
    for uid, e in entries.items():
        if e.get("source_ids", {}).get(source) == ext_id:
            return uid

    def _isti_portal_drugi_id(e):
        drugi = e.get("source_ids", {}).get(source)
        return drugi is not None and drugi != ext_id

    # 2. strict otisak
    uid = by_strict.get(fp_s)
    if uid is not None:
        e = entries[uid]
        if not _isti_portal_drugi_id(e):
            return uid
        # dupla objava na istom portalu — samo ako je i agencija ista
        if e.get("agencija") and e.get("agencija") == l.get("agencija"):
            return uid

    # 3. loose otisak + cena u toleranciji — SAMO preko izvora
    for uid in by_loose.get(fp_l, []):
        e = entries[uid]
        if _isti_portal_drugi_id(e):
            continue
        if _price_close(e.get("price_current"), l.get("cena")):
            return uid
    return None


def update(data_dir: Path, mode: str, listings: list, source: str = "halo",
           run_date: str = None, verbose: bool = True) -> dict:
    """Upise danasnji scrape u registar i vrati izvestaj.

    `listings` je lista zapisa u formatu koji vec pravi scrape.py
    (id, url, naslov, zgrada, agencija, struktura, m2, cena, cena_m2, sprat).
    """
    today = run_date or date.today().isoformat()
    reg = load_registry(data_dir, mode)
    entries = reg["entries"]
    by_strict, by_loose = _index(entries)

    seen_uids = set()
    n_new = n_merged = n_price = n_reopened = 0
    odbijeni = []

    for l in listings:
        ok, razlog = validan(l, mode)
        if not ok:
            odbijeni.append((l.get("id"), razlog))
            continue
        ext_id = str(l.get("id") or "")
        uid = _match(l, entries, by_strict, by_loose, source, ext_id)
        fp_s, fp_l = fingerprints(l)

        if uid is None:
            uid = _h("uid", source, ext_id, fp_l)
            entries[uid] = {
                "uid": uid,
                "first_seen": today,
                "last_seen": today,
                "is_active": True,
                "deactivated_at": None,
                "fp_loose": fp_l,
                "fp_strict_all": [fp_s],
                "sources": [source],
                "source_ids": {source: ext_id},
                "source_urls": [l.get("url")] if l.get("url") else [],
                "zgrada": l.get("zgrada"),
                "struktura": l.get("struktura"),
                "str_label": l.get("str_label"),
                "m2": l.get("m2"),
                "sprat": l.get("sprat"),
                "agencija": l.get("agencija"),
                "naslov": l.get("naslov"),
                "price_first": l.get("cena"),
                "price_current": l.get("cena"),
                "price_changes": [],
            }
            by_strict[fp_s] = uid
            by_loose.setdefault(fp_l, []).append(uid)
            n_new += 1
        else:
            e = entries[uid]
            if not e.get("is_active"):
                n_reopened += 1
            e["last_seen"] = today
            e["is_active"] = True
            e["deactivated_at"] = None

            if source not in e.get("sources", []):
                e.setdefault("sources", []).append(source)
                n_merged += 1
            e.setdefault("source_ids", {})[source] = ext_id
            if l.get("url") and l["url"] not in e.setdefault("source_urls", []):
                e["source_urls"].append(l["url"])
            if fp_s not in e.setdefault("fp_strict_all", []):
                e["fp_strict_all"].append(fp_s)
                by_strict[fp_s] = uid

            cena = l.get("cena")
            if cena and e.get("price_current") and cena != e["price_current"]:
                e.setdefault("price_changes", []).append({
                    "date": today, "from": e["price_current"], "to": cena,
                })
                e["price_current"] = cena
                n_price += 1
            elif cena and not e.get("price_current"):
                e["price_current"] = cena
                e.setdefault("price_first", cena)

            # osvezi opisna polja (agent moze da izmeni oglas)
            for k in ("naslov", "agencija", "m2", "sprat", "cena_m2"):
                if l.get(k) is not None:
                    e[k] = l[k]

        seen_uids.add(uid)

    # ── deaktivacija ─────────────────────────────────────────────────
    active_before = [u for u, e in entries.items() if e.get("is_active")]
    ratio = len(seen_uids) / len(active_before) if active_before else 1.0

    n_deact = 0
    skipped = False
    if ratio < MIN_SEEN_RATIO and active_before:
        skipped = True
        if verbose:
            print(f"  [STORE] Videli smo samo {len(seen_uids)}/{len(active_before)} "
                  f"aktivnih ({ratio:.0%}) — deaktivacija PRESKOCENA (sumnja na los scrape).")
    else:
        for uid in active_before:
            if uid in seen_uids:
                continue
            e = entries[uid]
            gap = (date.fromisoformat(today) - date.fromisoformat(e["last_seen"])).days
            if gap >= GRACE_DAYS:
                e["is_active"] = False
                e["deactivated_at"] = today
                n_deact += 1

    for uid, e in entries.items():
        e["days_listed"] = days_listed(e, today)

    save_registry(data_dir, mode, reg)

    if odbijeni:
        print(f"  [STORE] ODBIJENO {len(odbijeni)} zapisa (neispravni podaci):")
        for i, (oid, raz) in enumerate(odbijeni[:5]):
            print(f"           {oid}: {raz}")
        if len(odbijeni) > 5:
            print(f"           ... i jos {len(odbijeni)-5}")

    rep = {
        "date": today, "source": source, "odbijeno": len(odbijeni),
        "u_registru": len(entries),
        "videno": len(seen_uids),
        "novi": n_new,
        "spojeno_preko_izvora": n_merged,
        "promena_cene": n_price,
        "ponovo_aktivni": n_reopened,
        "deaktivirano": n_deact,
        "deaktivacija_preskocena": skipped,
        "aktivnih_sada": sum(1 for e in entries.values() if e.get("is_active")),
    }
    if verbose:
        print(f"  [STORE] {mode}: u registru {rep['u_registru']}, videno {rep['videno']}, "
              f"novih {rep['novi']}, spojeno {rep['spojeno_preko_izvora']}, "
              f"cena menjana {rep['promena_cene']}, deaktivirano {rep['deaktivirano']}")
    return rep


def days_listed(e: dict, today: str = None) -> int:
    """Trajanje oglasa u danima. Za aktivne = starost do danas."""
    today = today or date.today().isoformat()
    start = date.fromisoformat(e["first_seen"])
    end = date.fromisoformat(e["deactivated_at"] or e.get("last_seen") or today) \
        if not e.get("is_active") else date.fromisoformat(today)
    return max((end - start).days, 0)
