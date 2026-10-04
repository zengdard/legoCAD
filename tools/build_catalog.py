#!/usr/bin/env python3
"""Construit pieces_catalog.json : les dimensions réelles (en LDU et en studs)
des pièces curées, extraites des fichiers .dat de la bibliothèque LDraw officielle.

Une unité LDraw : 1 stud = 20 LDU de large ; hauteur d'une brique = 24 LDU,
hauteur d'une plaque = 8 LDU. Y pointe vers le bas dans les coordonnées LDraw.
"""
import json
import re
import sys
from pathlib import Path

LDRAW_PARTS = Path(__file__).resolve().parent.parent / "ldraw" / "ldraw" / "parts"

# Sous-ensemble curatif : briques, plaques, tuiles, pentes, rondes, baseplate.
# Les IDs inconnus ou introuvables sont signalés et ignorés.
CURATED_IDS = [
    # Briques
    "3005",  "3004",  "3622",  "3010",  "3009",  "3008",
    "3002",  "3003",  "3001",  "2456",  "3007",
    # Plaques
    "3024",  "3023",  "3623",  "3710",  "3666",  "3460",
    "3022",  "3020",  "3795",  "3034",  "3031",  "3035",
    # Tuiles (lisses)
    "3070b", "3069b", "63864", "2431",  "6636",
    "3068b", "87079", "26603",
    # Pentes
    "3040b", "3665",  "3043",  "3039",  "3298",  "3299",  "3037",
    "4286",  "4871",
    # Pièces rondes / cylindres
    "3062b", "3941",  "4032",  "3063",  "4589",
    # Divers utiles
    "3811",  "2465",  "6141",  "85861",
    # Briques rondes / murs
    "6233",  "6143",
]

# Couleurs LDraw standards (codes LDConfig) proposées au LLM.
COLORS = {
    "0":  {"name": "Black", "hex": "#05131D"},
    "1":  {"name": "Blue", "hex": "#0055BF"},
    "2":  {"name": "Green", "hex": "#237841"},
    "3":  {"name": "Dark Turquoise", "hex": "#00838F"},
    "4":  {"name": "Red", "hex": "#C91A09"},
    "5":  {"name": "Dark Pink", "hex": "#C870A0"},
    "6":  {"name": "Brown", "hex": "#583927"},
    "7":  {"name": "Light Gray", "hex": "#9BA19D"},
    "8":  {"name": "Dark Gray", "hex": "#6D6E5C"},
    "14": {"name": "Yellow", "hex": "#F2CD37"},
    "15": {"name": "White", "hex": "#FFFFFF"},
    "16": {"name": "(main color)", "hex": "#B4B4B4"},
    "17": {"name": "Light Green", "hex": "#A5CA18"},
    "18": {"name": "Light Yellow", "hex": "#FFCF0A"},
    "19": {"name": "Tan", "hex": "#E4CD9E"},
    "22": {"name": "Purple", "hex": "#81007B"},
    "25": {"name": "Orange", "hex": "#FE8A18"},
    "27": {"name": "Lime", "hex": "#BBE90B"},
    "28": {"name": "Dark Tan", "hex": "#958A73"},
    "29": {"name": "Bright Pink", "hex": "#E4ADC8"},
    "36": {"name": "Trans Red", "hex": "#C91A09", "translucent": True},
    "37": {"name": "Trans Neon Orange", "hex": "#FCAC00", "translucent": True},
    "43": {"name": "Trans Light Blue", "hex": "#A0EEF7", "translucent": True},
    "47": {"name": "Trans Clear", "hex": "#FCFCFC", "translucent": True},
    "70": {"name": "Reddish Brown", "hex": "#582A12"},
    "71": {"name": "Light Bluish Gray", "hex": "#A0A5A9"},
    "72": {"name": "Dark Bluish Gray", "hex": "#6C6E68"},
    "73": {"name": "Medium Bluish Gray", "hex": "#8A928D"},
    "84": {"name": "Medium Nougat", "hex": "#AA7D55"},
    "191": {"name": "Bright Light Orange", "hex": "#F8BB3D"},
    "226": {"name": "Bright Light Yellow", "hex": "#FFF03A"},
    "272": {"name": "Dark Blue", "hex": "#0A3463"},
    "288": {"name": "Dark Green", "hex": "#184632"},
    "308": {"name": "Dark Brown", "hex": "#352100"},
    "320": {"name": "Dark Red", "hex": "#720E0F"},
    "321": {"name": "Dark Azure", "hex": "#469BC3"},
    "322": {"name": "Medium Azure", "hex": "#69BBD5"},
    "323": {"name": "Light Aqua", "hex": "#DCFFFB"},
    "378": {"name": "Sand Green", "hex": "#A0BCAC"},
    "484": {"name": "Very Light Orange", "hex": "#FFA70C"},
    "503": {"name": "Very Light Gray", "hex": "#E6E3DA"},
}


def parse_part(path: Path):
    """Retourne (description, bbox) où bbox = (dx, dy, dz) en LDU."""
    desc = None
    minv = [float("inf")] * 3
    maxv = [float("-inf")] * 3

    def bbox_of_file(p: Path, depth=0):
        nonlocal desc
        lo = [float("inf")] * 3
        hi = [float("-inf")] * 3
        try:
            text = p.read_text(errors="replace")
        except OSError:
            return lo, hi
        for line in text.splitlines():
            tok = line.split()
            if not tok:
                continue
            if tok[0] == "0" and desc is None:
                after = " ".join(tok[1:])
                if after and not after.lower().startswith(("bfc", "name:", "author", "!ldraw")):
                    desc = after
            elif tok[0] in ("2", "3", "4", "5"):
                n = {"2": 2, "3": 3, "4": 4, "5": 2}[tok[0]]
                nums = [float(x) for x in tok[2:2 + 3 * n]]
                for i in range(n):
                    v = nums[3 * i:3 * i + 3]
                    for k in range(3):
                        lo[k] = min(lo[k], v[k])
                        hi[k] = max(hi[k], v[k])
            elif tok[0] == "1" and depth < 8:
                nums = [float(x) for x in tok[2:14]]
                sub = _resolve_sub(p.parent, tok[14])
                if sub and sub.exists():
                    slo, shi = bbox_of_file(sub, depth + 1)
                    for sx in (slo[0], shi[0]):
                        for sy in (slo[1], shi[1]):
                            for sz in (slo[2], shi[2]):
                                v = [
                                    nums[0] + nums[3] * sx + nums[4] * sy + nums[5] * sz,
                                    nums[1] + nums[6] * sx + nums[7] * sy + nums[8] * sz,
                                    nums[2] + nums[9] * sx + nums[10] * sy + nums[11] * sz,
                                ]
                                for k in range(3):
                                    lo[k] = min(lo[k], v[k])
                                    hi[k] = max(hi[k], v[k])
        return lo, hi

    lo, hi = bbox_of_file(path)
    if desc is None or hi[0] == float("-inf"):
        return None, None
    return desc, (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])


def _resolve_sub(base: Path, name: str):
    name = name.replace("\\", "/").lower()
    pdir = LDRAW_PARTS.parent / "p"
    if name.startswith("s/"):
        stem = name[2:]
        for d in (base, LDRAW_PARTS / "s", pdir / "s", pdir):
            cand = d / stem
            if cand.exists():
                return cand
        return None
    for cand in (LDRAW_PARTS / name, pdir / name):
        if cand.exists():
            return cand
    return None


def main():
    catalog = {}
    missing = []
    for pid in CURATED_IDS:
        path = LDRAW_PARTS / f"{pid}.dat"
        if not path.exists():
            missing.append(pid)
            continue
        desc, dims = parse_part(path)
        if not desc:
            missing.append(pid)
            continue
        dx, dy, dz = dims
        h24 = round(dy / 24, 3)   # hauteur en unités "brique" (24 LDU)
        catalog[pid] = {
            "id": pid,
            "desc": desc.strip(),
            "bbox_ldu": [round(dx), round(dy), round(dz)],
            "studs_x": round(dx / 20, 2),
            "studs_z": round(dz / 20, 2),
            "height_brick_units": h24,
            "kind": classify(pid, desc, h24),
        }
    out = Path(__file__).resolve().parent.parent / "pieces_catalog.json"
    out.write_text(json.dumps({"colors": COLORS, "parts": catalog}, indent=1))
    print(f"{len(catalog)} pièces cataloguées, {len(missing)} ignorées : {missing}")


def classify(pid, desc, h):
    d = desc.lower()
    if "baseplate" in d or "base plate" in d:
        return "baseplate"
    if h <= 0.5:
        return "tile" if "tile" in d else "plate"
    if "slope" in d or "roof" in d:
        return "slope"
    if "cylinder" in d or "round" in d:
        return "round"
    if "tile" in d:
        return "tile"
    return "brick"


if __name__ == "__main__":
    main()
