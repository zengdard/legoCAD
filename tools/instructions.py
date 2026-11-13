#!/usr/bin/env python3
"""Notice de montage imprimable (HTML) : le livrable qui rend le modèle réel.

Un .ldr n'est pas une notice. Ce module produit un document A4 imprimable :

  - couverture : titre, nombre de pièces, dimensions, aperçu 3D ;
  - inventaire : chaque pièce avec son icône, sa couleur, sa quantité ;
  - étapes numérotées : rendu LeoCAD de l'étape (pièces nouvelles
    surlignées, précédentes estompées via `--highlight --fade-steps`) et
    liste des pièces ajoutées ;
  - avertissements de disponibilité (couples pièce/couleur non observés
    dans les sets officiels).

Le HTML est autonome (hors images) et s'ouvre dans n'importe quel
navigateur ; « Imprimer → PDF » donne une notice. Si LeoCAD est absent,
les images sont omises et le document reste utilisable.
"""
from __future__ import annotations

import html
import shutil
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent

# Couleurs de base pour les icônes (les vraies couleurs viennent du catalogue)
_FALLBACK_HEX = "#C91A09"


def _colors() -> dict:
    import json
    try:
        return json.loads((PROJECT / "pieces_catalog.json").read_text())["colors"]
    except (OSError, ValueError, KeyError):
        return {}


def _part_height_plates(part: dict) -> int:
    from ldraw_model import part_levels
    return part_levels(part)


def part_icon(model, part_id: str, color: str, size: int = 54) -> str:
    """Petite icône SVG d'une pièce (vue de dessus + épaisseur)."""
    try:
        part = model.part(part_id)
    except Exception:
        part = {"studs_x": 2, "studs_z": 2, "desc": part_id, "kind": "brick"}
    sx = max(1, round(float(part.get("studs_x", 2))))
    sz = max(1, round(float(part.get("studs_z", 2))))
    h = _part_height_plates(part)
    hexcol = _colors().get(str(color), {}).get("hex", _FALLBACK_HEX)
    cell = 10
    top_w, top_h = sx * cell, sz * cell
    depth = max(4, h * 4)          # épaisseur visible (brique plus épaisse)
    pad = 3
    w = top_w + pad * 2
    ht = top_h + depth + pad * 2
    studs = []
    for ix in range(sx):
        for iz in range(sz):
            cx = pad + ix * cell + cell / 2
            cy = pad + iz * cell + cell / 2
            studs.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.6" '
                f'fill="#fff" fill-opacity=".45" stroke="#000" '
                f'stroke-opacity=".35" stroke-width=".6"/>')
    return (
        f'<svg class="icon" width="{size}" height="{size * ht / w:.0f}" '
        f'viewBox="0 0 {w} {ht}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect x="{pad}" y="{pad}" width="{top_w}" height="{top_h}" rx="1.5" '
        f'fill="{hexcol}" stroke="#000" stroke-opacity=".55"/>'
        f'<rect x="{pad}" y="{pad + top_h}" width="{top_w}" height="{depth}" '
        f'fill="{hexcol}" fill-opacity=".65" stroke="#000" '
        f'stroke-opacity=".35"/>'
        + "".join(studs) + "</svg>")


def _steps(model) -> list[tuple[int, int]]:
    if not model.bricks:
        return []
    if not model.steps:
        return [(0, len(model.bricks))]
    out, start = [], 0
    for end in model.steps:
        end = min(end, len(model.bricks))
        if end > start:
            out.append((start, end))
        start = end
    if start < len(model.bricks):
        out.append((start, len(model.bricks)))
    return out


def _added(rows) -> list[dict]:
    agg: dict[tuple, int] = {}
    for b in rows:
        key = (b["part_id"], b["color"])
        agg[key] = agg.get(key, 0) + 1
    out = [{"part_id": p, "color": c, "count": n}
           for (p, c), n in agg.items()]
    out.sort(key=lambda r: (-r["count"], r["part_id"]))
    return out


def render_step_images(ldr: Path, out_dir: Path, steps: list,
                       model=None, width: int = 900, height: int = 700,
                       lat: float = 28, lon: float = 38,
                       use_leocad: bool = True) -> list[Path | None]:
    """Une image par étape.

    LeoCAD d'abord (surbrillance des pièces nouvelles) ; s'il est absent ou
    échoue, on bascule sur le rendu SVG isométrique (`preview_svg`), qui
    fonctionne partout, y compris en ligne.
    """
    import render as rend
    import shutil
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    n_steps = len(steps)
    if not use_leocad and model is not None:
        import preview_svg
        return preview_svg.render_steps(model, out_dir, steps)
    frame = rend.frame_of(Path(ldr))
    cam = rend.camera_args(frame, lat, lon) if frame else \
        ["--camera-angles", str(lat), str(lon)]
    prefix = out_dir / "step.png"
    try:
        rend._run([str(ldr), "-i", str(prefix), "-w", str(width),
                   "-h", str(height), *cam, "-f", "1", "-t", str(n_steps),
                   "--fade-steps", "--highlight"])
    except RuntimeError:
        if model is not None:
            import preview_svg
            return preview_svg.render_steps(model, out_dir, steps)
        return [None] * n_steps
    found = {}
    for p in out_dir.glob("step*.png"):
        digits = p.stem[len("step"):]
        if digits.isdigit():
            found[int(digits)] = p
    paths = [found.get(k) for k in range(1, n_steps + 1)]
    if all(p is None for p in paths) and model is not None:
        import preview_svg
        return preview_svg.render_steps(model, out_dir, steps)
    return paths


_CSS = """
:root { --ink:#15171a; --muted:#6b7280; --line:#d7dbe0; --accent:#0a84ff; }
* { box-sizing: border-box; }
body { margin:0; font: 14px/1.45 -apple-system, "Segoe UI", Roboto, sans-serif;
       color:var(--ink); background:#fff; }
.page { width: 210mm; min-height: 297mm; padding: 14mm 14mm 12mm;
        margin: 0 auto; page-break-after: always; position: relative; }
.page:last-child { page-break-after: auto; }
h1 { font-size: 30px; margin: 0 0 4px; letter-spacing: -.02em; }
h2 { font-size: 20px; margin: 0 0 10px; }
h3 { font-size: 15px; margin: 0 0 6px; }
.sub { color: var(--muted); margin-bottom: 18px; }
.cover { display:flex; flex-direction:column; height: 269mm; }
.cover .art { flex:1; display:flex; align-items:center; justify-content:center; }
.cover img { max-width: 100%; max-height: 190mm; object-fit: contain; }
.kpis { display:flex; gap:10px; flex-wrap:wrap; margin: 10px 0 0; }
.kpi { border:1px solid var(--line); border-radius:10px; padding:8px 12px; }
.kpi b { display:block; font-size:18px; }
.kpi span { color:var(--muted); font-size:12px; }
table { width:100%; border-collapse: collapse; }
td, th { border-bottom:1px solid var(--line); padding:6px 8px; text-align:left;
         vertical-align:middle; }
th { font-size:11px; text-transform:uppercase; letter-spacing:.06em;
     color:var(--muted); }
td.qty { font-weight:700; width:42px; }
td.ico { width:64px; }
td.desc { color:var(--muted); font-size:12px; }
.step { display:grid; grid-template-columns: 1fr 240px; gap:14px;
        border:1px solid var(--line); border-radius:12px; padding:10px;
        margin-bottom:12px; break-inside: avoid; }
.step .num { font-size:11px; color:var(--muted); text-transform:uppercase;
             letter-spacing:.08em; }
.step img { width:100%; border-radius:8px; background:#1b1d21; }
.step .parts { display:flex; flex-wrap:wrap; gap:6px; align-content:flex-start; }
.step .parts .p { display:flex; align-items:center; gap:4px;
                  border:1px solid var(--line); border-radius:8px; padding:3px 5px;
                  font-size:11px; }
.step .parts b { font-size:13px; }
.warn { border-left:4px solid #f5a623; background:#fff8e8; padding:8px 10px;
        border-radius:0 8px 8px 0; margin:8px 0; font-size:12px; }
.chapter { grid-column:1/-1; border-top:2px solid var(--ink); padding-top:8px;
           margin:6px 0 2px; font-weight:800; text-transform:uppercase;
           letter-spacing:.08em; font-size:12px; }
.modules { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
.module { border:1px solid var(--line); border-radius:12px; padding:10px; }
.module img { width:100%; background:#1b1d21; border-radius:8px; }
.module h3 { margin:8px 0 0; }
.module .parts { display:flex; flex-wrap:wrap; gap:5px; margin-top:8px; }
.module .p { display:flex; align-items:center; gap:4px; border:1px solid var(--line);
             border-radius:8px; padding:2px 5px; font-size:11px; }
.foot { position:absolute; bottom:6mm; left:14mm; right:14mm; color:var(--muted);
        font-size:10px; display:flex; justify-content:space-between; }
@media print { body { background:#fff; } .page { margin:0; box-shadow:none; } }
"""


def build(model, ldr: Path, out_dir: str | Path, title: str | None = None,
          preview: Path | None = None, render_steps: bool = True,
          use_leocad: bool = True,
          availability: dict | None = None) -> Path:
    """Génère la notice HTML ; retourne le chemin du fichier."""
    import bom as bmod

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    esc = html.escape
    title = title or model.name
    rows = bmod.build(model)
    meta = bmod.totals(rows)
    steps = _steps(model)
    avail = availability if availability is not None else \
        bmod.check_availability(rows)

    # sous-ensembles (liaisons faibles) : modules à assembler à part
    import studs
    modules = studs.subassemblies(model)
    module_cards = []
    if modules:
        mod_dir = out / "modules"
        mod_dir.mkdir(parents=True, exist_ok=True)
        import preview_svg
        for mi, mod in enumerate(modules, start=1):
            svg = preview_svg.render_svg(model, indices=set(mod),
                                         title=f"module {mi}")
            p = mod_dir / f"module{mi:02d}.svg"
            p.write_text(svg, encoding="utf-8")
            counts = _added([model.bricks[i] for i in mod])
            chips = "".join(
                f'<div class="p">{part_icon(model, c["part_id"], c["color"], 30)}'
                f'<b>{c["count"]}×</b><span>{esc(c["part_id"])}</span></div>'
                for c in counts[:8])
            module_cards.append(
                f'<article class="module"><img src="modules/{p.name}" '
                f'alt="module {mi}"><h3>Sous-ensemble {mi}</h3>'
                f'<div class="sub">{len(mod)} pièces</div>'
                f'<div class="parts">{chips}</div></article>')
    modules_page = ""
    if module_cards:
        modules_page = ('<section class="page"><h2>Sous-ensembles</h2>'
                        '<div class="sub">Ces modules sont reliés au reste par '
                        'un seul stud : assemble-les à part, puis fixe-les au '
                        'modèle principal.</div>'
                        '<div class="modules">' + "".join(module_cards) +
                        '</div></section>')

    images: list[Path | None] = [None] * len(steps)
    if render_steps:
        images = render_step_images(Path(ldr), out / "steps", steps,
                                    model=model, use_leocad=use_leocad)
    if preview is None and (out / "preview.png").exists():
        preview = out / "preview.png"

    head = (f"<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
            f"<title>{esc(title)} — notice</title><style>{_CSS}</style></head>"
            f"<body>")

    kpis = "".join(
        f'<div class="kpi"><b>{v}</b><span>{k}</span></div>'
        for k, v in (("pièces", meta["parts"]), ("types", meta["types"]),
                     ("couleurs", meta["colors"]), ("étapes", len(steps)),
                     ("stabilité", f'{model.stability()["min_stability"]:.2f}')))
    art = f'<img src="{esc(str(Path(preview).name))}" alt="aperçu">' \
        if preview else ""
    cover = (f'<section class="page cover"><div><h1>{esc(title)}</h1>'
             f'<div class="sub">Notice de montage · générée par legoCAD</div>'
             f'<div class="kpis">{kpis}</div></div>'
             f'<div class="art">{art}</div></section>')

    # --- inventaire ----------------------------------------------------- #
    inv_rows = []
    for r in rows:
        inv_rows.append(
            f'<tr><td class="qty">{r.count}×</td>'
            f'<td class="ico">{part_icon(model, r.part_id, r.color)}</td>'
            f'<td><b>{esc(r.part_id)}</b><div class="desc">{esc(r.desc)}</div>'
            f'</td><td>{esc(r.color_name)}</td></tr>')
    warnings = []
    if avail.get("checked") and avail.get("unknown"):
        names = ", ".join(f"{u['part_id']}/{u['color_name']}"
                          for u in avail["unknown"][:12])
        warnings.append(
            f"Certaines combinaisons pièce/couleur n'ont pas été observées "
            f"dans les sets officiels analysés : {esc(names)}. "
            f"Vérifie leur disponibilité sur BrickLink/Rebrickable.")
    warn_html = "".join(f'<div class="warn">{w}</div>' for w in warnings)
    inventory = (f'<section class="page"><h2>Inventaire</h2>'
                 f'<div class="sub">{len(rows)} lignes de pièces, '
                 f'{meta["parts"]} pièces au total.</div>{warn_html}'
                 f'<table><thead><tr><th>Qté</th><th></th><th>Pièce</th>'
                 f'<th>Couleur</th></tr></thead><tbody>'
                 + "".join(inv_rows) + "</tbody></table></section>")

    # --- étapes --------------------------------------------------------- #
    step_pages = []
    cards = []
    max_y = max((b["y"] for b in model.bricks), default=0)
    chapter = None
    for k, ((a, b), img) in enumerate(zip(steps, images), start=1):
        level = max((model.bricks[i]["y"] for i in range(a, b)), default=0)
        label = ("Soubassement" if level <= 0 else
                 "Structure" if level < max_y - 2 else "Finitions")
        if label != chapter:
            chapter = label
            cards.append(
                f'<div class="chapter"><span>{esc(label)}</span></div>')
        added = _added(model.bricks[a:b])
        parts_html = "".join(
            f'<div class="p">{part_icon(model, p["part_id"], p["color"], 34)}'
            f'<b>{p["count"]}×</b><span>{esc(p["part_id"])}</span></div>'
            for p in added)
        img_html = f'<img src="steps/{img.name}" alt="étape {k}">' if img else ""
        cards.append(
            f'<div class="step"><div><div class="num">Étape {k} / '
            f'{len(steps)} · {esc(label)}</div>{img_html}</div>'
            f'<div><h3>Pièces ajoutées</h3><div class="parts">{parts_html}'
            f'</div></div></div>')
        if len(cards) == 4 or k == len(steps):
            step_pages.append(
                f'<section class="page"><h2>Montage</h2>'
                + "".join(cards) + f'<div class="foot"><span>Étapes {k - len(cards) + 1}'
                f'–{k}</span><span>{esc(title)}</span></div></section>')
            cards = []

    foot = ('<div class="foot"><span>legoCAD · pièces et couleurs réelles'
            '</span><span>Construis, vérifie, partage.</span></div>')
    doc = head + cover + inventory + modules_page + "".join(step_pages) + \
        foot + "</body></html>"
    path = out / "notice.html"
    path.write_text(doc, encoding="utf-8")
    return path


def main():
    import argparse
    import sys
    sys.path.insert(0, str(PROJECT / "tools"))
    from ldraw_model import LDrawModel
    ap = argparse.ArgumentParser(description="notice HTML d'un modèle .ldr")
    ap.add_argument("ldr")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()
    ldr = Path(args.ldr)
    # reconstruire le modèle à partir de sa nomenclature de voxels pour
    # disposer des métadonnées ; sinon on relit les briques du .ldr.
    import voxel
    from brickify import brickify, BrickifyOptions
    grid = voxel.from_ldr(ldr)
    model, _ = brickify(grid, ldr.stem, BrickifyOptions(add_steps=True))
    out = Path(args.out) if args.out else ldr.parent / f"{ldr.stem}_notice"
    out.mkdir(parents=True, exist_ok=True)
    rebuilt = out / f"{ldr.stem}.ldr"
    model.save(rebuilt)
    path = build(model, rebuilt, out, render_steps=True,
                 use_leocad=not args.no_render)
    print(f"notice : {path}")


if __name__ == "__main__":
    main()
