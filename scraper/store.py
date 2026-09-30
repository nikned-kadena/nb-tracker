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
Ako danasnji run donese manje od MIN_SEEN_RATIO aktivnih oglasa TOG IZVORA,
deaktivacija se NE izvrsava uopste. Ista filozofija kao STOP guard u
scraper-u: radije zastareli podaci nego pokvareni.

DEAKTIVACIJA JE PO IZVORU (ispravljeno 30.09.2026)
--------------------------------------------------
Jedan run obilazi JEDAN portal. Prva verzija je poredila danasnje vidjene
oglase sa SVIM aktivnim zapisima u registru, bez obzira na izvor — pa bi
dnevni Halo run, koji nosi vecinu i lako prodje ratio prag, posle dva dana
ugasio svaki oglas koji postoji samo na 4zida ili Nadji Dom-u. BnV registar
rente je vec imao 40 takvih zapisa: da ovo nije popravljeno, ugasili bi se
02.10. iako su zivi, i usli u DOM statistiku kao 40 lazno zavrsenih oglasa
sa trajanjem od par dana. Isto vazi obrnuto — 4zida run ne sme da gasi
Halo oglase.

Zato registar pamti dva dodatna podatka:

  reg["last_run"][izvor]        kad je taj portal poslednji put obidjen
  e["last_seen_src"][izvor]     kad je taj oglas poslednji put vidjen na njemu

Oglas se gasi tek kad je "mrtav" na SVIM svojim izvorima: za svaki izvor
mora postojati obilazak posle poslednjeg vidjenja, i razmak mora biti bar
GRACE_DAYS. Izvor koji odavno nije pokrenut (Nadji Dom se ne vrti dnevno)
ne moze da ugasi nista — sto je tacno, jer o njemu nemamo novu informaciju.

Stari zapisi nemaju `last_seen_src`; pri prvom prolazu se popunjava iz
`last_seen` za sve izvore tog zapisa, pa migracija ne trazi backfill.
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
        return {"schema_version": SCHEMA_VERSION, "mode": mode,
                "entries": {}, "last_run": {}}
    d = json.loads(p.read_text(encoding="utf-8"))
    d.setdefault("entries", {})
    d.setdefault("last_run", {})     # izvor -> datum poslednjeg obilaska
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
        # Loose otisak sadrzi zgradu, a zgrada se moze naknadno prepoznati
        # (vidi _bolja_zgrada). Zato se cuvaju SVE varijante, da oglas ostane
        # spojiv i po starom otisku iz dana kad je bio neidentifikovan.
        for fp in (e.get("fp_loose_all") or [e.get("fp_loose")]):
            if fp:
                by_loose.setdefault(fp, []).append(uid)
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


def _neid(z) -> bool:
    """Da li je vrednost zgrade prazna ili 'neidentifikovano'."""
    return not z or "neidentifikovano" in str(z).lower()


def _bolja_zgrada(stara, nova) -> bool:
    """Sme li `nova` da zameni `staru`?

    SAMO NAGORE — neidentifikovano/prazno -> konkretan naziv. Nikad obrnuto.

    Zasto je ovo pravilo, a ne prosto prepisivanje (nadjeno 30.09.2026):
    `zgrada` do sada uopste nije bila medju poljima koja se osvezavaju na
    postojecem zapisu. Kad je uvedeno prepoznavanje zgrade iz opisa agenta,
    ekstrakcija je radila (54/61 oglasa je dobilo pravi tekst), ali je u
    registru i dalje stajalo staro "BW (neidentifikovano)" — pa je izgledalo
    kao da ceo posao nije uspeo. Popravka mora biti jednosmerna: kad isti
    stan dodje sa drugog portala gde naslov ne kaze zgradu, ne sme da obrise
    zgradu koju je jaci izvor vec tacno prepoznao.
    """
    if not nova or _neid(nova):
        return False
    return _neid(stara)


def _migriraj_last_seen_src(e: dict):
    """Stari zapis nema `last_seen_src` — popuni ga iz `last_seen`.

    Pretpostavka je konzervativna: svaki izvor tog zapisa je oglas video
    poslednji put kad i registar u celini. Time nijedan stari oglas ne
    postane odmah "mrtav na izvoru" samo zato sto polje nije postojalo.
    """
    if not e.get("last_seen_src"):
        ls = e.get("last_seen")
        e["last_seen_src"] = {s: ls for s in (e.get("sources") or ["halo"])}
    else:
        for s in (e.get("sources") or []):
            e["last_seen_src"].setdefault(s, e.get("last_seen"))


def _mrtav_na_izvoru(e: dict, izvor: str, last_run: dict, today: str) -> bool:
    """Da li je oglas potvrdjeno nestao sa jednog portala."""
    kad_obidjen = last_run.get(izvor)
    if not kad_obidjen:
        return False        # taj portal jos nije ni pokrenut — ne znamo nista
    vidjen = (e.get("last_seen_src") or {}).get(izvor) or e.get("last_seen")
    if not vidjen:
        return False
    if kad_obidjen <= vidjen:
        return False        # nema novijeg obilaska od poslednjeg vidjenja
    razmak = (date.fromisoformat(kad_obidjen) - date.fromisoformat(vidjen)).days
    return razmak >= GRACE_DAYS


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
    n_new = n_merged = n_price = n_reopened = n_zgrada = 0
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
                "fp_loose_all": [fp_l],
                "fp_strict_all": [fp_s],
                "sources": [source],
                "last_seen_src": {source: today},
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
            _migriraj_last_seen_src(e)
            e["last_seen_src"][source] = today
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

            # zgrada se osvezava samo nagore (vidi _bolja_zgrada)
            if _bolja_zgrada(e.get("zgrada"), l.get("zgrada")):
                e["zgrada"] = l["zgrada"]
                n_zgrada += 1
                # Nova zgrada = nov loose otisak. Stari se zadrzava u listi,
                # da oglas ostane spojiv i preko zapisa koji jos nemaju
                # prepoznatu zgradu.
                if fp_l not in e.setdefault("fp_loose_all", [e.get("fp_loose")]):
                    e["fp_loose_all"].append(fp_l)
                    by_loose.setdefault(fp_l, []).append(uid)
                e["fp_loose"] = fp_l

        seen_uids.add(uid)

    # ── deaktivacija ─────────────────────────────────────────────────
    # Prag se racuna SAMO nad oglasima koje ovaj izvor uopste moze da vidi.
    # Ranije se poredilo sa celim registrom, pa je 4zida run sa 60 oglasa
    # naspram 300 aktivnih uvek padao ispod praga i nikad nista nije gasio,
    # dok je Halo run prolazio prag i gasio tudje oglase.
    reg.setdefault("last_run", {})[source] = today

    na_ovom_izvoru = [u for u, e in entries.items()
                      if e.get("is_active") and source in (e.get("sources") or [])]
    videni_ovde = seen_uids & set(na_ovom_izvoru)
    ratio = (len(videni_ovde) / len(na_ovom_izvoru)) if na_ovom_izvoru else 1.0

    n_deact = 0
    skipped = False
    if ratio < MIN_SEEN_RATIO and na_ovom_izvoru:
        skipped = True
        if verbose:
            print(f"  [STORE] Na izvoru '{source}' videli smo samo "
                  f"{len(videni_ovde)}/{len(na_ovom_izvoru)} aktivnih ({ratio:.0%}) "
                  f"— deaktivacija PRESKOCENA (sumnja na los scrape).")
    else:
        for uid, e in entries.items():
            if not e.get("is_active") or uid in seen_uids:
                continue
            _migriraj_last_seen_src(e)
            izvori = e.get("sources") or []
            if not izvori:
                continue
            # gasi se tek kad ga nema ni na jednom svom portalu
            if all(_mrtav_na_izvoru(e, s, reg["last_run"], today) for s in izvori):
                e["is_active"] = False
                e["deactivated_at"] = today
                n_deact += 1
                # Izvor koji se ne vrti dnevno (Nadji Dom, 4zida) ume da
                # stoji nedeljama. Tada znamo da je oglas nestao NEGDE u tom
                # razmaku, ne bas danas. Obelezi to da DOM statistika moze
                # da odvoji pouzdane od procenjenih trajanja.
                razmaci = []
                for s in izvori:
                    v = (e.get("last_seen_src") or {}).get(s)
                    o = reg["last_run"].get(s)
                    if v and o:
                        razmaci.append(
                            (date.fromisoformat(o) - date.fromisoformat(v)).days)
                if razmaci and min(razmaci) > 2 * GRACE_DAYS:
                    e["deactivation_uncertain"] = True
                    e["deactivation_window_days"] = min(razmaci)

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
        "zgrada_dopunjena": n_zgrada,
        "deaktivirano": n_deact,
        "deaktivacija_preskocena": skipped,
        "aktivnih_sada": sum(1 for e in entries.values() if e.get("is_active")),
    }
    if verbose:
        print(f"  [STORE] {mode}: u registru {rep['u_registru']}, videno {rep['videno']}, "
              f"novih {rep['novi']}, spojeno {rep['spojeno_preko_izvora']}, "
              f"cena menjana {rep['promena_cene']}, deaktivirano {rep['deaktivirano']}"
              + (f", zgrada dopunjena {rep['zgrada_dopunjena']}"
                 if rep['zgrada_dopunjena'] else ""))
    return rep


def days_listed(e: dict, today: str = None) -> int:
    """Trajanje oglasa u danima. Za aktivne = starost do danas."""
    today = today or date.today().isoformat()
    start = date.fromisoformat(e["first_seen"])
    end = date.fromisoformat(e["deactivated_at"] or e.get("last_seen") or today) \
        if not e.get("is_active") else date.fromisoformat(today)
    return max((end - start).days, 0)


# ── samotest ────────────────────────────────────────────────────────────
# `python3 scraper/store.py` — provera pravila deaktivacije po izvoru.
# Radi u privremenom folderu, ne dira data/.

if __name__ == "__main__":
    import tempfile

    def _og(i, src):
        return {"id": f"{src}:{i}", "url": f"http://{src}/{i}",
                "naslov": f"stan {i}", "zgrada": "BW Perla",
                "agencija": f"AG{i}", "struktura": "2.0",
                "str_label": "Dvosoban", "m2": 60 + i, "cena": 1500 + i * 10,
                "sprat": str(i % 10), "mode": "renta"}

    palo = []
    with tempfile.TemporaryDirectory() as tmp:
        D = Path(tmp)
        M = "renta"
        update(D, M, [_og(i, "halo") for i in range(1, 11)],
               source="halo", run_date="2026-09-01", verbose=False)
        update(D, M, [_og(i, "4zida") for i in range(11, 15)],
               source="4zida", run_date="2026-09-01", verbose=False)

        # 1. tri dnevna Halo run-a ne smeju da ugase 4zida oglase
        for d in ("2026-09-02", "2026-09-03", "2026-09-04"):
            update(D, M, [_og(i, "halo") for i in range(1, 11)],
                   source="halo", run_date=d, verbose=False)
        reg = load_registry(D, M)
        z = [e for e in reg["entries"].values() if e["sources"] == ["4zida"]]
        if sum(1 for e in z if e["is_active"]) != 4:
            palo.append("Halo run je ugasio 4zida oglase")

        # 2. oglas skinut sa Halo-a se gasi posle GRACE_DAYS
        for d in ("2026-09-05", "2026-09-06", "2026-09-07"):
            update(D, M, [_og(i, "halo") for i in range(1, 10)],
                   source="halo", run_date=d, verbose=False)
        reg = load_registry(D, M)
        h10 = [e for e in reg["entries"].values()
               if e["source_ids"].get("halo") == "halo:10"][0]
        if h10["is_active"] or h10["deactivated_at"] != "2026-09-06":
            palo.append(f"Halo oglas #10 nije ugasen kako treba: {h10['deactivated_at']}")

        # 3. redak izvor gasi svoje tek kad se ponovo pokrene, uz oznaku
        update(D, M, [_og(i, "4zida") for i in (11, 12)],
               source="4zida", run_date="2026-09-08", verbose=False)
        reg = load_registry(D, M)
        mrtvi = [e for e in reg["entries"].values()
                 if e["sources"] == ["4zida"] and not e["is_active"]]
        if len(mrtvi) != 2:
            palo.append(f"4zida nije ugasio svoja dva oglasa (ugaseno {len(mrtvi)})")
        elif not all(e.get("deactivation_uncertain") for e in mrtvi):
            palo.append("nedostaje oznaka deactivation_uncertain za redak izvor")
        if sum(1 for e in reg["entries"].values()
               if "halo" in e["sources"] and e["is_active"]) != 9:
            palo.append("4zida run je dirao Halo oglase")

        # 4. oglas na dva portala se gasi tek kad ga OBA demantuju
        update(D, M, [_og(20, "halo")], source="halo",
               run_date="2026-09-09", verbose=False)
        update(D, M, [dict(_og(20, "4zida"), m2=80, cena=1700)],
               source="4zida", run_date="2026-09-09", verbose=False)
        for d in ("2026-09-11", "2026-09-13", "2026-09-15"):
            update(D, M, [_og(i, "halo") for i in range(1, 10)],
                   source="halo", run_date=d, verbose=False)
        reg = load_registry(D, M)
        duo = [e for e in reg["entries"].values() if len(e["sources"]) > 1]
        if len(duo) != 1:
            palo.append(f"spajanje preko izvora nije radilo ({len(duo)} zapisa)")
        elif not duo[0]["is_active"]:
            palo.append("oglas na dva portala ugasen samo na osnovu Halo-a")
        else:
            update(D, M, [_og(i, "4zida") for i in (11, 12)],
                   source="4zida", run_date="2026-09-16", verbose=False)
            reg = load_registry(D, M)
            duo = [e for e in reg["entries"].values() if len(e["sources"]) > 1]
            if duo[0]["is_active"]:
                palo.append("oglas nije ugasen ni kad su ga oba portala demantovala")

        # 5. zgrada se dopunjuje naknadno, ali samo nagore
        update(D, M, [dict(_og(30, "4zida"), zgrada="BW (neidentifikovano)")],
               source="4zida", run_date="2026-09-17", verbose=False)
        reg = load_registry(D, M)
        u30 = [u for u, e in reg["entries"].items()
               if e["source_ids"].get("4zida") == "4zida:30"][0]
        if not _neid(reg["entries"][u30]["zgrada"]):
            palo.append("test 5: pocetno stanje nije neidentifikovano")
        # isti oglas, sad sa prepoznatom zgradom iz opisa
        rep = update(D, M, [dict(_og(30, "4zida"), zgrada="BW Thalia")],
                     source="4zida", run_date="2026-09-18", verbose=False)
        reg = load_registry(D, M)
        if reg["entries"][u30]["zgrada"] != "BW Thalia":
            palo.append("zgrada NIJE dopunjena kad je prepoznata iz opisa")
        if rep.get("zgrada_dopunjena") != 1:
            palo.append("izvestaj ne broji dopunjene zgrade")
        # drugi portal bez naziva ne sme da je obrise
        update(D, M, [dict(_og(30, "halo"), m2=90, cena=1800,
                           zgrada="BW (neidentifikovano)")],
               source="halo", run_date="2026-09-18", verbose=False)
        reg = load_registry(D, M)
        if reg["entries"][u30]["zgrada"] != "BW Thalia":
            palo.append("slabiji izvor je obrisao vec prepoznatu zgradu")

    if palo:
        print("PALO:")
        for p in palo:
            print("  -", p)
        raise SystemExit(1)
    print("store.py: sve provere prolaze (5/5) — deaktivacija po izvoru + dopuna zgrade")
