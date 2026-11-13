#!/usr/bin/env python3
"""Télécharge un échantillon du corpus OMR (sets officiels) pour calibrer la
disponibilité des pièces et servir de banc d'essai.

Source : https://github.com/vdirienzo/ldrawomr (analyse de l'OMR, les modèles
eux-mêmes sont distribués par Rebrickable/la communauté, redistribution
CCAL — voir la licence LDraw). On ne versionne **pas** les modèles : ce script
les met en cache localement, puis `tools/availability.py --build` agrège des
statistiques (couples pièce/couleur) qui, elles, sont versionnées.

    python3 tools/fetch_omr.py --out /tmp/omr/sets --limit 500
    python3 tools/availability.py --build /tmp/omr/sets
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

API = "https://api.github.com/repos/vdirienzo/ldrawomr/contents/corpus"
DIRS = ("mpds_modern", "mpds_classic", "mpds_kids", "mpds_specialty",
        "mpds_licensed", "mpds_technic")


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "legoCAD-omr"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def fetch(out: Path, limit: int = 300, min_kb: int = 2,
          max_kb: int = 120, per_theme: int = 60) -> int:
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for theme in DIRS:
        try:
            items = [x for x in _get(f"{API}/{theme}")
                     if x["name"].endswith(".mpd")]
        except Exception as exc:                       # thème absent
            print(f"{theme}: ignoré ({exc})")
            continue
        items.sort(key=lambda x: x.get("size", 0))
        pick = [x for x in items
                if min_kb * 1024 <= x.get("size", 0) <= max_kb * 1024]
        for x in pick[:per_theme]:
            target = out / x["name"]
            if target.exists():
                continue
            try:
                urllib.request.urlretrieve(x["download_url"], target)
                n += 1
            except Exception as exc:
                print(f"{x['name']}: échec ({exc})")
            if n >= limit:
                return n
            time.sleep(0.02)
        print(f"{theme}: {min(per_theme, len(pick))} sets")
    return n


def main():
    ap = argparse.ArgumentParser(description="échantillon OMR pour la disponibilité")
    ap.add_argument("--out", default="/tmp/omr/sets")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--min-kb", type=int, default=2)
    ap.add_argument("--max-kb", type=int, default=120)
    ap.add_argument("--per-theme", type=int, default=60)
    args = ap.parse_args()
    n = fetch(Path(args.out), args.limit, args.min_kb, args.max_kb,
              args.per_theme)
    print(f"{n} fichiers dans {args.out}")
    print("puis : python3 tools/availability.py --build", args.out)


if __name__ == "__main__":
    main()
