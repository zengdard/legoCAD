#!/usr/bin/env python3
"""Banc visuel 8 vues — le protocole de la galerie BrickBench.

Chaque modèle est rendu sous 8 angles (45°), avec une vue frontale marquée,
une planche contact et des métriques de silhouette calculées sur le masque :

  - occupation : part de l'image couverte par le modèle ;
  - symétrie   : IoU entre le masque et son miroir gauche-droite ;
  - contour    : périmètre / sqrt(aire), complexité de la silhouette ;
  - dos        : occupation de la vue opposée (contrôle « dos non vide »).

C'est un outil d'**audit de design**, pas un juge : il rend visibles les
scènes plates ou les dos non finis, comme le fait la galerie.

    python3 tools/views.py --ldr out/web/chateau/chateau.ldr \
        --out out/web/chateau/views
    python3 tools/make_model.py --shape castle --name chateau --views
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import render  # noqa: E402


def mask_from_image(img: Image.Image, threshold: int = 22) -> Image.Image:
    """Masque binaire du modèle : pixels différents du fond (coin haut-gauche)."""
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, bg)
    return diff.convert("L").point(lambda v: 255 if v > threshold else 0)


def silhouette_metrics(mask: Image.Image, bbox=None) -> dict:
    """Occupation, symétrie, complexité de contour d'un masque binaire."""
    w, h = mask.size
    n = w * h
    stat = ImageStat.Stat(mask)
    area = stat.sum[0] / 255.0
    occupancy = area / n
    flip = mask.transpose(Image.FLIP_LEFT_RIGHT)
    inter = ImageChops.multiply(mask, flip)
    union = ImageChops.lighter(mask, flip)
    i_area = ImageStat.Stat(inter).sum[0] / 255.0
    u_area = ImageStat.Stat(union).sum[0] / 255.0
    symmetry = i_area / u_area if u_area else 0.0
    edges = mask.filter(ImageFilter.FIND_EDGES)
    perimeter = ImageStat.Stat(edges).sum[0] / 255.0
    contour = perimeter / math.sqrt(area) if area else 0.0
    box = bbox or mask.getbbox()
    return {
        "occupancy": round(occupancy, 4),
        "symmetry": round(symmetry, 4),
        "contour": round(contour, 3),
        "bbox": list(box) if box else None,
        "area_px": int(area),
    }


def render_views(ldr: str | Path, out_dir: str | Path, n: int = 8,
                 size: int = 1024, lat: float = 20.0) -> dict:
    """Rend `n` vues, la planche contact et le JSON de métriques."""
    ldr = Path(ldr)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    views, masks = [], []
    for i in range(n):
        lon = round(i * 360.0 / n, 1)
        png = out / f"view_{i:02d}.png"
        render.render_image(ldr, png, width=size, height=size,
                            lat=lat, lon=lon)
        img = Image.open(png).convert("RGB")
        mask = mask_from_image(img)
        m = silhouette_metrics(mask)
        m["angle"] = lon
        m["front"] = (i == 0)
        views.append(m)
        masks.append((img, mask))

    # planche contact 4×2
    cols = 4
    tw = 384
    rows = (n + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (tw + 26) + 46),
                      (24, 26, 30))
    draw = ImageDraw.Draw(sheet)
    draw.text((12, 12), f"{ldr.stem} — {n} vues", fill=(235, 238, 242))
    for i, (img, mask) in enumerate(masks):
        thumb = img.resize((tw, tw), Image.LANCZOS)
        x = (i % cols) * tw
        y = 46 + (i // cols) * (tw + 26)
        sheet.paste(thumb, (x, y))
        label = f"{i:02d}  {views[i]['angle']:.0f}°"
        if views[i]["front"]:
            label += "  FRONT"
            draw.rectangle([x + 2, y + 2, x + tw - 3, y + tw - 3],
                           outline=(255, 196, 64), width=4)
        draw.text((x + 6, y + tw + 4), label, fill=(220, 224, 230))
    contact = out / "contact.png"
    sheet.save(contact)

    front = views[0]["occupancy"] if views else 0.0
    back = views[n // 2]["occupancy"] if n >= 2 else 0.0
    result = {
        "model": ldr.stem,
        "views": views,
        "contact": str(contact),
        "average_occupancy": round(
            sum(v["occupancy"] for v in views) / max(1, len(views)), 4),
        "min_symmetry": round(min((v["symmetry"] for v in views),
                                  default=0.0), 4),
        "back_non_empty": bool(front and back >= 0.35 * front),
        "notes": ("plusieurs vues : un dos vide ou une silhouette plate "
                  "se voient ici"),
    }
    (out / "views.json").write_text(json.dumps(result, indent=2,
                                               ensure_ascii=False))
    return result


def main():
    ap = argparse.ArgumentParser(description="banc visuel 8 vues")
    ap.add_argument("--ldr", required=True)
    ap.add_argument("--out", default=None)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--size", type=int, default=1024)
    ap.add_argument("--lat", type=float, default=20.0)
    args = ap.parse_args()
    out = Path(args.out) if args.out else \
        PROJECT / "out" / "views" / Path(args.ldr).stem
    res = render_views(args.ldr, out, args.n, args.size, args.lat)
    print(json.dumps({k: res[k] for k in
                      ("model", "average_occupancy", "min_symmetry",
                       "back_non_empty")}, ensure_ascii=False))
    print(res["contact"])


if __name__ == "__main__":
    main()
