#!/usr/bin/env python3
"""Pipeline complet : forme/volume → modèle constructible → livrables.

    python3 tools/make_model.py --shape house --name maison
    python3 tools/make_model.py --shape rocket --name fuse --video
    python3 tools/make_model.py --vox models/maison.vox.json
    python3 tools/make_model.py --ldr models/Voilier.ldr --name voilier
    python3 tools/make_model.py --image photo.jpg --name portrait
    python3 tools/make_model.py --shape duck --no-render        # sans LeoCAD

Sorties (dans out/web/<nom>/) :
    <nom>.ldr              modèle LDraw (ouvrable dans Studio/LeoCAD)
    preview.png            aperçu 3D
    notice.html            notice A4 imprimable (inventaire + étapes)
    <nom>.bom.csv/json     liste de courses
    <nom>.wanted_list.xml  wanted list BrickLink
    report.json            métriques + score + contrôles

Le pipeline est volontairement sans LLM : la forme est explicite (volume),
la compilation en briques est déterministe et vérifiée. Le mode texte
(`tools/text_to_voxel.py`) branche un LLM en amont, mais il ne place jamais
de briques : il produit un volume, que ce pipeline valide.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import bom as bmod                 # noqa: E402
import brickify                    # noqa: E402
import ldr_io                     # noqa: E402
import instructions as notice      # noqa: E402
import quality                     # noqa: E402
import shapes                      # noqa: E402
import voxel                       # noqa: E402
from brickify import BrickifyOptions  # noqa: E402


def _grid_from_args(args) -> tuple[voxel.VoxelGrid, str]:
    if args.shape:
        kwargs = {}
        if args.width and args.shape in ("house", "brick"):
            kwargs["width"] = args.width
        elif args.width:
            kwargs["height"] = args.width
        if args.shape == "mosaic":
            if not args.image:
                raise SystemExit("--shape mosaic nécessite --image")
            kwargs["image"] = args.image
        return shapes.make(args.shape, **kwargs), args.shape
    if args.image:
        return shapes.mosaic(args.image, max_width=args.width or 48), \
            Path(args.image).stem
    if args.ldr:
        return voxel.from_ldr(args.ldr), Path(args.ldr).stem
    if args.vox:
        return voxel.VoxelGrid.load(args.vox), Path(args.vox).stem
    raise SystemExit("indique --shape, --vox, --ldr ou --image")


def run(args) -> dict:
    if getattr(args, "ldr_native", False) and args.ldr:
        return _run_native(args)
    grid, default_name = _grid_from_args(args)
    name = args.name or default_name
    grid = grid.normalize()
    sx, sy, sz = grid.size()
    if grid.count() > 60_000 or max(sx, sy, sz) > 96:
        raise ValueError(
            f"volume trop grand ({sx}×{sy}×{sz}, {grid.count()} voxels) : "
            "réduis l'échelle, décime le modèle ou choisis un set plus petit")
    print(f"[volume] {grid.count()} voxels, taille {(sx, sy, sz)}", flush=True)

    opts = BrickifyOptions(tiles_on_top=not args.no_tiles,
                           tile_cap=not getattr(args, "no_tile_cap", False),
                           bond="stack" if args.stack else "running",
                           add_steps=True,
                           max_parts_per_step=args.parts_per_step)
    model, report = brickify.brickify(grid, name, opts)
    print(f"[briques] {report['pieces']} pièces, couverture "
          f"{report['coverage']:.1%}, {report['islands']} amas, "
          f"stabilité {report['min_stability']:.2f}", flush=True)

    models_dir = PROJECT / "models"
    models_dir.mkdir(exist_ok=True)
    ldr = models_dir / f"{name}.ldr"
    model.save(ldr)

    out = PROJECT / "out" / "web" / _slug(name)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ldr, out / ldr.name)

    bom = bmod.export_all(model, out, name, online=bool(getattr(args, "rebrickable", False)))
    avail = bom["meta"]["availability"]

    # aperçu : SVG isométrique immédiat, puis LeoCAD si disponible (plus joli)
    preview = None
    try:
        import preview_svg
        preview = out / "preview.svg"
        preview_svg.save_svg(model, preview, title=name)
        print(f"[aperçu] {preview}", flush=True)
    except Exception as exc:
        print(f"[aperçu] SVG ignoré : {exc}", flush=True)
    if not args.no_render:
        try:
            import render as rend
            png = out / "preview.png"
            rend.render_image(ldr, png, width=1100, height=820,
                              lat=30, lon=42)
            preview = png
            print(f"[rendu] {preview}", flush=True)
        except Exception as exc:                     # LeoCAD absent/erreur
            print(f"[rendu] LeoCAD ignoré : {exc}", flush=True)

    notice_path = None
    if not args.no_notice:
        notice_path = notice.build(
            model, ldr, out, title=name, preview=preview,
            render_steps=not args.no_notice_render,
            use_leocad=not args.no_render,
            availability=avail)
        print(f"[notice] {notice_path}", flush=True)

    pdf_path = None
    if getattr(args, "pdf", False):
        try:
            import pdf_notice
            pdf_path = pdf_notice.build(out / ldr.name, out / f"{name}.pdf")
            print(f"[pdf] {pdf_path}", flush=True)
        except Exception as exc:
            print(f"[pdf] ignoré : {exc}", flush=True)

    if args.video and not args.no_render:
        try:
            import render as rend
            rend.build_video(ldr, out / f"{name}.mp4", lat=30)
        except Exception as exc:
            print(f"[vidéo] ignorée : {exc}", flush=True)

    sc = quality.score(model, report, bom["meta"], avail)
    result = {
        "name": name,
        "ldr": str(out / ldr.name),
        "preview": str(preview) if preview else None,
        "notice": str(notice_path) if notice_path else None,
        "pdf": str(pdf_path) if pdf_path else None,
        "bom": bom["meta"],
        "bricks": report,
        "score": sc,
        "report": str(out / "report.json"),
    }
    (out / "report.json").write_text(json.dumps(result, indent=2,
                                                ensure_ascii=False))
    print(f"[score] {quality.summary_line(sc)}", flush=True)
    return result


def _run_native(args) -> dict:
    """Import d'un .ldr en conservant les pièces (pas de recompilation)."""
    src = Path(args.ldr)
    name = args.name or src.stem
    model, stats = ldr_io.load(src, name)
    if not model.bricks:
        raise ValueError("aucune pièce axis-aligned importable dans ce fichier")
    # ordre de montage : on ne réordonne que si le modèle est entièrement
    # relié par des studs (les charnières/axes ne sont pas modélisés)
    import build_order as bo
    import stability
    import studs
    rep = studs.report(model)
    if not rep["unsupported"] and rep["islands"] == 1:
        steps = bo.plan(model)
        if not bo.validate(model, steps):
            bo.apply(model, steps)
    models_dir = PROJECT / "models"
    models_dir.mkdir(exist_ok=True)
    ldr = models_dir / f"{name}.ldr"
    model.save(ldr)
    out = PROJECT / "out" / "web" / _slug(name)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ldr, out / ldr.name)
    bom = bmod.export_all(model, out, name, online=bool(getattr(args, "rebrickable", False)))
    stab = stability.analyze(model)
    preview = out / "preview.svg"
    try:
        import preview_svg
        preview_svg.save_svg(model, preview, title=name)
    except Exception:
        preview = None
    notice_path = None
    pdf_path = None
    if getattr(args, "pdf", False):
        try:
            import pdf_notice
            pdf_path = pdf_notice.build(out / ldr.name, out / f"{name}.pdf")
        except Exception as exc:
            print(f"[pdf] ignoré : {exc}", flush=True)
    if not args.no_notice:
        notice_path = notice.build(model, ldr, out, title=name,
                                   preview=preview,
                                   render_steps=not args.no_notice_render,
                                   use_leocad=not args.no_render,
                                   availability=bom["meta"]["availability"])
    report = {
        "status": "OK" if rep["unsupported"] == [] else "IMPORT_PARTIAL",
        "pieces": len(model.bricks),
        "types": len(model.parts_summary()),
        "coverage": 1.0, "gaps": [], "gap_count": 0,
        "build_steps": max(1, len(model.steps)),
        "build_errors": [],
        "islands": rep["islands"],
        "connections": rep["connections"],
        "min_stability": stab["min_stability"],
        "unsupported": rep["unsupported"],
        "tipping_joints": stab.get("tipping_joints", []),
        "single_stud": len(stab.get("single_stud", [])),
        "removed_cells": 0,
        "import": stats,
        "collisions": stats.get("collisions", 0),
        "skipped_rotated": stats.get("skipped_rotated", 0),
        "bounds": model.bounds(),
    }
    sc = quality.score(model, report, bom["meta"],
                       bom["meta"]["availability"])
    result = {
        "name": name, "ldr": str(out / ldr.name),
        "preview": str(preview) if preview else None,
        "notice": str(notice_path) if notice_path else None,
        "pdf": str(pdf_path) if pdf_path else None,
        "bom": bom["meta"], "bricks": report, "score": sc,
        "report": str(out / "report.json"), "source": {"mode": "ldr-native"},
    }
    (out / "report.json").write_text(json.dumps(result, indent=2,
                                                ensure_ascii=False))
    print(f"[import] {report['pieces']} pièces, {rep['islands']} amas, "
          f"{len(rep['unsupported'])} non attachées", flush=True)
    print(f"[score] {quality.summary_line(sc)}", flush=True)
    return result


def _slug(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return keep.strip("_") or "model"


def main():
    ap = argparse.ArgumentParser(
        description="forme/volume → modèle LEGO constructible + notice")
    src = ap.add_argument_group("source")
    src.add_argument("--shape", choices=sorted(shapes.SHAPES))
    src.add_argument("--vox", help="fichier .vox.json / .vox.txt")
    src.add_argument("--ldr", help="modèle LDraw à recompiler")
    src.add_argument("--ldr-native", action="store_true",
                     help="importer les pièces d'origine (sans recompiler)")
    src.add_argument("--image", help="image → mosaïque")
    ap.add_argument("--name")
    ap.add_argument("--width", type=int, default=None)
    ap.add_argument("--parts-per-step", type=int, default=12)
    ap.add_argument("--no-tiles", action="store_true")
    ap.add_argument("--no-tile-cap", action="store_true")
    ap.add_argument("--stack", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--no-notice", action="store_true")
    ap.add_argument("--no-notice-render", action="store_true")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--pdf", action="store_true",
                    help="notice PDF via LPub3D (si installé)")
    ap.add_argument("--rebrickable", action="store_true",
                    help="vérifier la disponibilité en ligne (REBRICKABLE_API_KEY)")
    ap.add_argument("--json", action="store_true", help="sortie JSON seule")
    args = ap.parse_args()
    result = run(args)
    if not args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
