#!/usr/bin/env python3
"""
backfill_from_git.py — rekonstruise registar iz GIT istorije `latest_*.json`.

ZASTO POSTOJI ODVOJENO OD backfill_registry.py
----------------------------------------------
BnV pise dnevne snapshot fajlove (`snapshot_{mode}_YYYY-MM-DD.json`), pa se
tamo registar moze rekonstruisati direktno iz njih.

NB ih NE pise. On prepisuje `latest_halo_{mode}.json` svaki dan i cuva samo
agregatne brojeve u `history_halo_{mode}.json` — dakle po oglasu nema nista.
Da smo se oslonili samo na snapshot fajlove, NB bi DOM statistiku dobio tek
za nekoliko meseci.

Ali svaki dnevni `latest_*.json` je commitovan u git. Git tako sadrzi punu
dnevnu istoriju po oglasu — samo je treba procitati. Ovaj skript prolazi
`git log` za taj fajl, vadi svaku dnevnu verziju i pusta je kroz istu
`store.update()` logiku, hronoloski.

Radi za OBA repo-a:
    # NB
    python scraper/backfill_from_git.py --file data/latest_halo_prodaja.json --mode prodaja
    python scraper/backfill_from_git.py --file data/latest_halo_renta.json   --mode renta
    # BnV
    python scraper/backfill_from_git.py --file data/latest_prodaja.json --mode prodaja
    python scraper/backfill_from_git.py --file data/latest_renta.json   --mode renta

Pokrece se JEDNOM, pre prvog pravog run-a sa store slojem.

OGRANICENJE
-----------
Ako je istog dana bilo vise commit-ova, uzima se POSLEDNJI tog dana.
Dani bez commit-a su rupe u seriji i skript ih ispisuje — oglasi
deaktivirani neposredno posle rupe dobijaju `deactivation_uncertain`,
jer ne znamo kog tacno dana su skinuti.
"""

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import store  # noqa: E402


def _git(args, repo: Path):
    r = subprocess.run(["git", "-C", str(repo)] + args,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout


def verzije_po_danu(repo: Path, rel_path: str):
    """Vrati [(datum, sha)] — po jedan (poslednji) commit za svaki dan."""
    out = _git(["log", "--follow", "--format=%H|%cI", "--", rel_path], repo)
    po_danu = {}
    for line in out.strip().splitlines():
        if "|" not in line:
            continue
        sha, iso = line.split("|", 1)
        d = iso[:10]
        # git log ide od najnovijeg; prvi vidjen za dan je i poslednji tog dana
        po_danu.setdefault(d, sha)
    return sorted(po_danu.items())


def run(repo: Path, rel_path: str, mode: str, source: str = "halo",
        force: bool = False):
    data_dir = repo / "data"
    reg_path = data_dir / f"registry_{mode}.json"
    if reg_path.exists() and not force:
        print(f"[GIT-BACKFILL] {reg_path.name} vec postoji — necu ga pregaziti. "
              f"Dodaj --force ako zelis iz nule.")
        return {}
    if force and reg_path.exists():
        reg_path.unlink()

    try:
        verzije = verzije_po_danu(repo, rel_path)
    except RuntimeError as e:
        print(f"[GIT-BACKFILL] git greska: {e}", file=sys.stderr)
        return {}

    if not verzije:
        print(f"[GIT-BACKFILL] Nema commit-ova za {rel_path}.")
        return {}

    print(f"[GIT-BACKFILL] {rel_path} — {len(verzije)} dana "
          f"({verzije[0][0]} → {verzije[-1][0]})")

    gaps, prev_d, n_l, n_skip, n_prazno = [], None, 0, 0, 0
    for d_str, sha in verzije:
        d = date.fromisoformat(d_str)
        if prev_d and (d - prev_d).days > 1:
            gaps.append({"od": prev_d.isoformat(), "do": d_str,
                         "dana": (d - prev_d).days - 1})
        prev_d = d

        try:
            blob = _git(["show", f"{sha}:{rel_path}"], repo)
            snap = json.loads(blob)
        except Exception as e:
            n_skip += 1
            print(f"  ⚠ {d_str} ({sha[:7]}) preskocen: {str(e)[:80]}")
            continue

        listings = snap.get("listings", [])
        if not listings:
            # Prazan dan = scrape koji nije doneo nista. NE deaktiviramo po
            # njemu (isti razlog kao MIN_SEEN_RATIO u store.py), ali to mora
            # da se VIDI — tiho preskakanje je klasa greske koja nas je vec
            # kostala deset dana u avgustu 2026.
            n_prazno += 1
            print(f"  ⚠ {d_str}: fajl ima 0 oglasa — dan preskocen "
                  f"(nije se racunao ni kao odsustvo oglasa).")
            continue
        n_l += len(listings)
        store.update(data_dir, mode, listings, source=source,
                     run_date=d_str, verbose=False)

    reg = store.load_registry(data_dir, mode)
    gap_ends = {g["do"] for g in gaps}
    n_unc = 0
    for e in reg["entries"].values():
        if e.get("deactivated_at") in gap_ends:
            e["deactivation_uncertain"] = True
            n_unc += 1
    store.save_registry(data_dir, mode, reg)

    ent = reg["entries"]
    aktivni = sum(1 for e in ent.values() if e.get("is_active"))
    print(f"  → procitano {n_l} zapisa iz {len(verzije)-n_skip-n_prazno} dnevnih verzija"
          + (f" | {n_skip} necitljivih" if n_skip else "")
          + (f" | {n_prazno} praznih" if n_prazno else ""))
    print(f"  → registar: {len(ent)} oglasa ({aktivni} aktivnih, "
          f"{len(ent)-aktivni} skinutih)")
    if gaps:
        uk = sum(g["dana"] for g in gaps)
        print(f"  ⚠ RUPE: {len(gaps)}, ukupno {uk} dana bez commit-a")
        for g in gaps[:10]:
            print(f"      {g['od']} → {g['do']}  ({g['dana']} dana)")
        if len(gaps) > 10:
            print(f"      ... i jos {len(gaps)-10}")
        print(f"  ⚠ {n_unc} oglasa sa nesigurnim vremenom skidanja.")
    return {"oglasa": len(ent), "aktivnih": aktivni, "rupe": gaps}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True,
                    help="putanja fajla u repo-u, npr. data/latest_halo_prodaja.json")
    ap.add_argument("--mode", required=True, choices=["prodaja", "renta"])
    ap.add_argument("--source", default="halo")
    ap.add_argument("--repo", default=None, help="koren repo-a (podrazumevano: roditelj scraper/)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    repo = Path(a.repo) if a.repo else Path(__file__).parent.parent
    run(repo.resolve(), a.file, a.mode, a.source, a.force)
