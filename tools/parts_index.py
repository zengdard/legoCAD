#!/usr/bin/env python3
"""Index de la bibliothèque LDraw complète (~25 000 pièces) : descriptions,
familles et hauteurs nominales, avec cache disque. Permet de chercher une
pièce par son nom au lieu de la recopier depuis un sous-ensemble figé.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
LDRAW_PARTS = PROJECT / "ldraw" / "ldraw" / "parts"
_CACHE = PROJECT / "parts_index_cache.json"

# Familles reconnues, par priorité de regex sur la description LDraw.
# La hauteur nominale est en LDU (brique 24, plaque 8, etc.).
_FAMILY_PATTERNS = [
    ("baseplate", re.compile(r"baseplate|base plate", re.I), 8),
    ("minifig", re.compile(r"minifig|mini doll", re.I), 0),
    ("slope", re.compile(r"slope|roof tile|inverted", re.I), 24),
    ("cone", re.compile(r"cone", re.I), 48),
    ("cylinder", re.compile(r"cylinder", re.I), 24),
    ("round", re.compile(r"round", re.I), 24),
    ("wheel", re.compile(r"wheel|tyre|tire", re.I), 0),
    ("technic", re.compile(r"technic|pin |axle|gear", re.I), 24),
    ("tile", re.compile(r"tile", re.I), 8),
    ("plate", re.compile(r"plate", re.I), 8),
    ("brick", re.compile(r"brick", re.I), 24),
]

# Familles à exclure du placement automatique (géométrie non conforme à la
# grille briques ou hauteur non gérée) mais retournables par la recherche.
_INFO_ONLY = {"minifig", "wheel"}

_DESC_RE = re.compile(r"^0\s+(?!\!)([^~=_\d].+?)\s*$", re.M)
_NAME_RE = re.compile(r"^0 Name:\s*(\S+)", re.M)
Moved_RE = re.compile(r"~Moved to (\S+)")


def _classify(desc: str) -> tuple[str, int]:
    for fam, pat, h in _FAMILY_PATTERNS:
        if pat.search(desc):
            return fam, h
    return "other", 24


def scan_library(force: bool = False) -> dict:
    """Retourne {part_id: {"desc", "family", "height_ldu"}} pour toutes les
    pièces principales (pas les primitives ni les shortcuts avec ~_)."""
    if _CACHE.exists() and not force:
        return json.loads(_CACHE.read_text())
    index = {}
    for p in LDRAW_PARTS.glob("*.dat"):
        pid = p.stem.lower()
        if not pid[0].isdigit():
            continue  # primitives (box5.dat...) et alias non numériques
        try:
            head = p.read_text(errors="replace")[:600]
        except OSError:
            continue
        m = _NAME_RE.search(head)
        if m and m.group(1).lower() != p.name.lower():
            continue  # alias renommé : on garde le fichier officiel
        dm = _DESC_RE.search(head)
        if not dm:
            continue
        desc = dm.group(1).strip()
        if desc.startswith("~") or Moved_RE.search(desc):
            continue
        fam, h = _classify(desc)
        index[pid] = {"desc": desc, "family": fam, "height_ldu": h}
    _CACHE.write_text(json.dumps(index))
    return index


_INDEX: dict | None = None


def index() -> dict:
    global _INDEX
    if _INDEX is None:
        _INDEX = scan_library()
    return _INDEX


def search(query: str, family: str | None = None, limit: int = 20) -> list[dict]:
    """Recherche plein-texte insensible à la casse sur les descriptions.
    Tous les mots du query doivent être présents (ordre indifférent)."""
    terms = [t for t in re.split(r"\W+", query.lower()) if t]
    results = []
    for pid, info in index().items():
        if family and info["family"] != family:
            continue
        d = info["desc"].lower()
        if all(t in d for t in terms):
            results.append({"id": pid, "desc": info["desc"],
                            "family": info["family"],
                            "height_ldu": info["height_ldu"]})
    results.sort(key=lambda r: (len(r["desc"]), r["id"]))
    return results[:max(1, limit)]


def get(part_id: str) -> dict | None:
    return index().get(part_id.lower())


if __name__ == "__main__":
    import sys
    idx = scan_library(force="--force" in sys.argv)
    fams = {}
    for info in idx.values():
        fams[info["family"]] = fams.get(info["family"], 0) + 1
    print(f"{len(idx)} pièces indexées : {fams}")
    for r in search("brick 2 x 4", limit=3):
        print("  ", r)
