#!/usr/bin/env python3
"""Image → volume : carte de profondeur (depth map) → relief LEGO.

C'est le maillon « vision » du pipeline. Un modèle de profondeur monculaire
(DepthAnything, MiDaS, Depth Pro…) produit une image en niveaux de gris ;
ce module la transforme en **relief 2.5D** : chaque pixel devient une colonne
de plaques, avec la couleur de la photo. Un fond de briques rend le relief
soulevable et constructible.

    # depth map déjà calculée
    python3 tools/depth_to_voxel.py --depth profondeur.png --color photo.jpg \\
        --width 32 --max-height 18 --out models/relief.vox.json

    # brancher un modèle externe (DepthAnything, MiDaS, etc.)
    python3 tools/depth_to_voxel.py --image photo.jpg \\
        --depth-cmd "python3 mon_depth.py {image} {depth}" --width 32

Le résultat se compile avec `make_model.py --vox ...` (pentes et tiles
comprises). Ce n'est pas une reconstruction 3D complète : c'est un bas-relief,
la forme la plus robuste et la plus constructible à partir d'une seule image.
Les silhouettes multi-vues (`voxel.from_silhouettes`) restent disponibles pour
un objet vu de face/côté/dessus.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageFilter

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

from voxel import VoxelGrid, nearest_color  # noqa: E402


def from_depth(depth: str | Path, color: str | Path | None = None,
               width: int = 32, max_height: int = 18,
               backing: int = 3, invert: bool = False,
               min_height: int = 0, mask: str | Path | None = None,
               auto_mask: float | None = None) -> VoxelGrid:
    """Relief 2.5D : colonnes de plaques + fond de briques.

    `depth` : image en niveaux de gris (clair = proche = haut).
    `color` : image couleur optionnelle (mêmes proportions).
    `backing` : épaisseur du fond en plaques (0 = pas de fond).
    """
    d = Image.open(depth).convert("L")
    scale = width / max(1, d.width)
    w = max(1, round(d.width * scale))
    h = max(1, round(d.height * scale))
    d = d.resize((w, h)).filter(ImageFilter.MedianFilter(3))
    dp = d.load()
    cp = None
    if color:
        c = Image.open(color).convert("RGBA").resize((w, h))
        cp = c.load()
    mp = None
    if mask:
        m = Image.open(mask).convert("L").resize((w, h))
        mp = m.load()
    grid = VoxelGrid()
    if backing:
        grid.box(0, 0, 0, w, backing, h, "72")
    for z in range(h):
        for x in range(w):
            v = dp[x, z] / 255.0
            if invert:
                v = 1.0 - v
            height = round(v * max_height)
            if height <= min_height:
                continue
            if auto_mask is not None and v < auto_mask:
                continue
            if mp is not None and mp[x, z] < 128:
                continue
            col = "15"
            if cp is not None:
                r, g, b, a = cp[x, z]
                if a < 24:
                    continue
                col = nearest_color((r, g, b))
            for y in range(backing, backing + height):
                grid.add(x, y, h - 1 - z, col)
    return grid.normalize()


def make_depth(image: str | Path, cmd: str, out: str | Path) -> Path:
    """Exécute un modèle de profondeur externe (hook générique).

    `cmd` doit contenir `{image}` et `{depth}` ; exemple :
      "python3 tools/depth_anything.py {image} {depth}"
    """
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    command = cmd.replace("{image}", str(Path(image).resolve())) \
                 .replace("{depth}", str(out.resolve()))
    # pas de shell : la commande est découpée en arguments
    subprocess.run(command.split(), check=True, timeout=600)
    if not out.exists():
        raise RuntimeError(f"le modèle de profondeur n'a pas écrit {out}")
    return out


def main():
    ap = argparse.ArgumentParser(description="depth map → relief LEGO")
    ap.add_argument("--depth", help="image de profondeur (niveaux de gris)")
    ap.add_argument("--image", help="image source (si --depth-cmd)")
    ap.add_argument("--color", help="image couleur pour les voxels")
    ap.add_argument("--depth-cmd", default=None,
                    help='commande externe avec {image} et {depth}')
    ap.add_argument("--width", type=int, default=32)
    ap.add_argument("--max-height", type=int, default=18)
    ap.add_argument("--backing", type=int, default=3)
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--mask", help="masque (SAM/U2Net) : noir = fond ignoré")
    ap.add_argument("--auto-mask", type=float, default=None,
                    help="seuil de profondeur (0..1) pour ignorer le fond")
    ap.add_argument("--min-height", type=int, default=0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    depth = args.depth
    if args.depth_cmd:
        if not args.image:
            ap.error("--depth-cmd nécessite --image")
        tmp = Path(args.out).with_suffix(".depth.png")
        depth = make_depth(args.image, args.depth_cmd, tmp)
    if not depth:
        ap.error("indique --depth ou --depth-cmd")
    grid = from_depth(depth, args.color, args.width, args.max_height,
                      args.backing, args.invert, args.min_height,
                      mask=args.mask, auto_mask=args.auto_mask)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    grid.save(out)
    print(f"{out} : {grid.count()} voxels, taille {grid.size()}")


if __name__ == "__main__":
    main()
