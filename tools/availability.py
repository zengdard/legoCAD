#!/usr/bin/env python3
"""Disponibilité réelle des pièces : quels couples pièce/couleur existent ?

Le contrôle le plus utile pour un modèle « à construire » n'est pas la
géométrie mais l'**approvisionnement** : une brique 2x8 en rose fluorescent
n'existe peut-être jamais. Sans API en ligne, on apprend la disponibilité
sur un corpus de sets officiels (OMR = Official Model Repository) :

  - `data/part_colors.json` : {pièce: {couleur: occurrences}} + fréquence
    globale des pièces, construit par `tools/availability.py --build`.
  - `check(rows)` : part des couples pièce/couleur du modèle déjà observés.

Ce n'est pas une preuve d'existence (un set peut utiliser une combinaison
rare) mais c'est un signal honnête, hors ligne et reproductible. En ligne,
on peut compléter avec l'API Rebrickable (`REBRICKABLE_API_KEY`).

Format :
{
  "meta": {"source": "...", "sets": 200, "pieces": 15836, "date": "..."},
  "parts": {"3023": {"0": 143, "15": 65, ...}},
  "part_freq": {"3023": 833, ...},
  "color_freq": {"0": 3225, ...}
}
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "data" / "part_colors.json"
OMR_REPO = "https://github.com/vdirienzo/ldrawomr"


def scan_dir(directory: str | Path) -> dict:
    """Compte les couples pièce/couleur d'un dossier de .ldr/.mpd."""
    from voxel import _expand, _ldr_lines

    parts: dict[str, dict[str, int]] = {}
    part_freq: Counter = Counter()
    color_freq: Counter = Counter()
    sets, pieces = 0, 0
    for path in sorted(Path(directory).rglob("*")):
        if path.suffix.lower() not in (".ldr", ".mpd"):
            continue
        try:
            models, root = _ldr_lines(path)
        except OSError:
            continue
        n = 0
        for color, _pos, _mat, pid in _expand(root, models):
            parts.setdefault(pid, {})
            parts[pid][color] = parts[pid].get(color, 0) + 1
            part_freq[pid] += 1
            color_freq[color] += 1
            n += 1
        if n:
            sets += 1
            pieces += n
    return {
        "meta": {"source": OMR_REPO, "sets": sets, "pieces": pieces,
                 "date": date.today().isoformat(),
                 "note": "couples observés dans des sets officiels (OMR)"},
        "parts": {k: dict(sorted(v.items(), key=lambda kv: -kv[1]))
                  for k, v in parts.items()},
        "part_freq": dict(part_freq.most_common()),
        "color_freq": dict(color_freq.most_common()),
    }


def save(table: dict, path: str | Path = DATA) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, ensure_ascii=False, separators=(",", ":")))
    return path


def load(path: str | Path = DATA) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}


def observed(table: dict, part_id: str, color: str) -> int:
    return int(table.get("parts", {}).get(part_id, {}).get(color, 0))


def main():
    import argparse
    ap = argparse.ArgumentParser(description="disponibilité pièce/couleur (OMR)")
    ap.add_argument("--build", metavar="DOSSIER",
                    help="scanner un dossier de .ldr/.mpd et écrire data/part_colors.json")
    ap.add_argument("--out", default=str(DATA))
    ap.add_argument("--query", nargs=2, metavar=("PIECE", "COULEUR"),
                    help="vérifier un couple")
    args = ap.parse_args()
    if args.build:
        table = scan_dir(args.build)
        path = save(table, args.out)
        print(f"{path} : {table['meta']['sets']} sets, "
              f"{table['meta']['pieces']} pièces, "
              f"{len(table['parts'])} pièces distinctes")
        return
    table = load(args.out)
    if args.query:
        pid, color = args.query
        print(f"{pid} / {color} : {observed(table, pid, color)} occurrence(s)")
        return
    print(f"{args.out} : {table.get('meta', {})}")


if __name__ == "__main__":
    main()
