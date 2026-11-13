#!/usr/bin/env python3
"""Vérification en ligne de la disponibilité réelle (API Rebrickable v3).

Le corpus OMR donne une disponibilité **observée** ; l'API Rebrickable donne
la disponibilité **catalogue** (quelles couleurs existent pour une pièce,
dans combien de sets, prix indicatifs). Les deux sont complémentaires.

    export REBRICKABLE_API_KEY=...
    python3 tools/rebrickable.py --check 3001 4
    python3 tools/rebrickable.py --set 10698 | head

Aucune dépendance (urllib). Cache disque dans out/.rebrickable_cache.json.
Sans clé, le module ne fait rien et le pipeline retombe sur le corpus local.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
CACHE = PROJECT / "out" / ".rebrickable_cache.json"
BASE = "https://rebrickable.com/api/v3/lego"


def _colors() -> dict:
    try:
        return json.loads((PROJECT / "pieces_catalog.json").read_text())["colors"]
    except (OSError, ValueError, KeyError):
        return {}


class Rebrickable:
    def __init__(self, api_key: str | None = None):
        self.key = api_key or os.environ.get("REBRICKABLE_API_KEY")
        self.cache = {}
        if CACHE.exists():
            try:
                self.cache = json.loads(CACHE.read_text())
            except ValueError:
                self.cache = {}

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _get(self, path: str, params: dict | None = None) -> dict:
        if not self.key:
            raise RuntimeError("REBRICKABLE_API_KEY manquante")
        url = f"{BASE}/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        if url in self.cache:
            return self.cache[url]
        req = urllib.request.Request(url, headers={
            "Authorization": f"key {self.key}",
            "Accept": "application/json",
            "User-Agent": "legoCAD/2.0",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        self.cache[url] = data
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(self.cache))
        return data

    def part_colors(self, part_num: str) -> list[dict]:
        data = self._get(f"parts/{part_num}/colors/")
        return data.get("results", [])

    def part(self, part_num: str) -> dict:
        return self._get(f"parts/{part_num}/")

    def set_parts(self, set_num: str) -> list[dict]:
        out, page = [], 1
        while True:
            data = self._get(f"sets/{set_num}/parts/",
                             {"page": page, "page_size": 200})
            out += data.get("results", [])
            if not data.get("next"):
                break
            page += 1
        return out

    def has_color(self, part_num: str, ldraw_color: str) -> bool | None:
        """La pièce existe-t-elle dans cette couleur ? None si non vérifiable."""
        colors = _colors()
        name = str(colors.get(str(ldraw_color), {}).get("name", "")).lower()
        if not name:
            return None
        try:
            existing = {c.get("color_name", "").lower()
                        for c in self.part_colors(part_num)}
        except Exception:
            return None
        return any(name == c or name in c or c in name for c in existing)

    def verify_rows(self, rows) -> dict:
        """Vérifie en ligne les couples pièce/couleur non observés localement."""
        if not self.available:
            return {"checked": False, "reason": "pas de clé Rebrickable"}
        verified, refuted = 0, []
        for r in rows:
            ok = self.has_color(r.part_id, r.color)
            if ok is True:
                verified += 1
            elif ok is False:
                refuted.append({"part_id": r.part_id, "color": r.color,
                                "color_name": r.color_name})
        return {"checked": True, "verified": verified,
                "refuted": refuted,
                "score": round(verified / max(1, len(rows)), 3)}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Rebrickable (disponibilité réelle)")
    ap.add_argument("--check", nargs=2, metavar=("PIECE", "COULEUR_LDRAW"))
    ap.add_argument("--set", dest="set_num")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()
    rb = Rebrickable()
    if not rb.available:
        raise SystemExit("export REBRICKABLE_API_KEY=... (clé gratuite sur "
                         "rebrickable.com/api)")
    if args.check:
        pid, color = args.check
        colors = _colors()
        name = colors.get(str(color), {}).get("name", color)
        print(f"{pid} / {name} :", rb.has_color(pid, color))
        print("couleurs catalogue :",
              [c.get("color_name") for c in rb.part_colors(pid)][:20])
    elif args.set_num:
        parts = rb.set_parts(args.set_num)
        for p in parts[:args.limit]:
            print(p.get("part", {}).get("part_num"),
                  p.get("color", {}).get("name"), p.get("quantity"))
        print(f"... {len(parts)} lignes")
    else:
        ap.error("utilise --check PIECE COULEUR ou --set NUMERO")


if __name__ == "__main__":
    main()
