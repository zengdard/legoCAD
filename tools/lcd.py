#!/usr/bin/env python3
"""Modèles LeoCAD 0.7 (.lcd) : rendu, nomenclature et galerie.

Les archives Classic Space de marutan.net sont au vieux format LeoCAD 0.7.
LeoCAD 25 les ouvre encore en headless : on peut donc en extraire une image
et la **nomenclature réelle** (`-csv`), sans passer par l'interface. C'est un
excellent corpus de référence : proportions, palette, variété de pièces.

On ne convertit pas les .lcd en .ldr (l'export n'est pas exposé en CLI) ;
on les utilise comme **références visuelles et statistiques**, et comme
source d'inspiration pour les formes générées (`shapes.spaceship`).

    python3 tools/lcd.py --gallery "/home/.../clspace" --limit 12
    # -> out/web/gallery/index.html + PNG + BOM JSON
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
LEOCAD = ["flatpak", "run", "--filesystem=host", "org.leocad.LeoCAD"]

# quelques sets emblématiques (numéro -> nom)
NAMES = {
    "0442": "Space Probe", "0452": "Mobile Ground Tracking Station",
    "0462": "Rocket Launcher", "0483": "Alpha-1 Rocket Base",
    "0493": "Galaxy Explorer", "0497": "Galaxy Explorer",
    "0885": "Space Skiff", "0886": "Space Buggy", "0918": "Space Transport",
    "1498": "Space Dart", "1499": "Space Fighter", "1557": "Space Crawler",
    "1558": "Space Walker", "1580": "Space Laser", "6750": "Sonic Robot",
    "6780": "Space Transport", "6783": "Space Plane", "6801": "Space Scooter",
    "6802": "Space Probe", "6820": "Starfire I", "6821": "Meteor Monitor",
    "6822": "Space Digger", "6823": "Surface Transport", "6824": "Space Dart",
    "6825": "Cosmic Comet", "6826": "Space Swat", "6827": "Strata Scooter",
    "6841": "Mineral Detector", "6842": "Shuttle Craft", "6844": "Sismological Vehicle", "6845": "Cosmic Charger", "6846": "Solar Transporter",
    "6847": "Space Dozer", "6848": "Space Shuttle", "6849": "Space Probe",
    "6870": "Space Probe Launcher", "6871": "Star Patrol Launcher",
    "6872": "Xenon X-Craft", "6874": "Moonrover", "6880": "Surface Explorer",
    "6881": "Lunar Rocket Launcher", "6882": "Surface Rover",
    "6883": "Terrestrial Rover", "6890": "Cosmic Cruiser",
    "6891": "Gamma V Laser Craft", "6892": "Modular Space Transport",
    "6901": "Mobile Lab", "6926": "Mobile Recovery", "6927": "All-Terrain Vehicle", "6928": "M-Tron", "6929": "Star Fleet Voyager",
    "6930": "Space Supply Station", "6931": "Galactic Titan",
    "6940": "Alien Moon Stalker", "6950": "Mobile Rocket Transport",
    "6951": "Robot Command Center", "6952": "Solar Power Transporter",
    "6970": "Beta-1 Command Base", "6971": "Inter-Galactic Command Base",
    "6972": "Polaris Space Lab", "6980": "Galaxy Commander",
    "6985": "Cosmic Fleet Voyager",
}


def _run(args: list[str]) -> None:
    res = subprocess.run(LEOCAD + args, cwd=str(PROJECT), capture_output=True,
                         text=True, timeout=180, shell=False)
    if res.returncode != 0:
        err = "\n".join(l for l in res.stderr.splitlines()
                        if "Gtk-Message" not in l and "qpa.plugin" not in l
                        and "wl_display" not in l)
        raise RuntimeError(err or f"LeoCAD a échoué ({res.returncode})")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT.resolve()))
    except ValueError:
        return str(path)


def render(lcd: Path, png: Path, width: int = 900, height: int = 700) -> Path:
    png.parent.mkdir(parents=True, exist_ok=True)
    _run([str(lcd.resolve()), "-i", _rel(png), "-w", str(width),
          "-h", str(height)])
    return png


def bom(lcd: Path, csv_path: Path) -> list[dict]:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _run([str(lcd.resolve()), "-csv", _rel(csv_path)])
    rows = []
    if not csv_path.exists():
        return rows
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            try:
                qty = int(row.get("Quantity") or 0)
            except ValueError:
                qty = 0
            if qty:
                rows.append({"name": row.get("Part Name", ""),
                             "color": row.get("Color", ""),
                             "color_code": row.get("Color Code", ""),
                             "part_id": row.get("Part ID", "").replace(
                                 ".dat", ""),
                             "count": qty})
    return rows


def gallery(src: str | Path, out: str | Path, limit: int = 12,
            names: dict | None = None, only: list[str] | None = None) -> Path:
    src = Path(src)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    names = names or NAMES
    files = sorted(src.glob("*.lcd"))
    if only:
        wanted = {str(k).lower().replace(".lcd", "") for k in only}
        files = [f for f in files if f.stem.lower() in wanted]
    elif limit:
        files = files[:limit]
    cards = []
    index = []
    for lcd in files:
        key = lcd.stem.split("-")[0]
        label = names.get(key, "Classic Space")
        png = out / f"{lcd.stem}.png"
        csv_path = out / f"{lcd.stem}.csv"
        try:
            if not png.exists():
                render(lcd, png)
            rows = bom(lcd, csv_path)
        except Exception as exc:
            print(f"{lcd.name}: ignoré ({exc})")
            continue
        if not png.exists():
            continue
        total = sum(r["count"] for r in rows)
        colors = sorted({r["color"] for r in rows})
        index.append({"set": lcd.stem, "name": label, "pieces": total,
                      "colors": colors, "png": png.name,
                      "bom": [r for r in rows]})
        top = sorted(rows, key=lambda r: -r["count"])[:3]
        top_html = "<br>".join(
            f"{r['count']}× {html.escape(r['name'])} "
            f"({html.escape(r['color'])})" for r in top)
        cards.append(f'''<article class="card">
  <img src="{html.escape(png.name)}" alt="{html.escape(label)}">
  <h3>{html.escape(key)} — {html.escape(label)}</h3>
  <p>{total} pièces · {len(colors)} couleurs</p>
  <p class="small">{top_html}</p>
</article>''')
    (out / "index.json").write_text(json.dumps(index, indent=2,
                                               ensure_ascii=False))
    page = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>Galerie Classic Space — legoCAD</title>
<link rel="stylesheet" href="/static/gallery.css"></head><body>
<header><a href="/">← legoCAD</a><h1>Galerie Classic Space</h1>
<p>Modèles LeoCAD issus de <a href="https://www.marutan.net/arcsite/lego/index.php">
marutan.net</a>, rendus et inventoriés automatiquement. Ils servent de
référence de style et de proportions — le pipeline les analyse, il ne les
copie pas.</p></header>
<main>{''.join(cards)}</main>
<footer>Rendus LeoCAD · nomenclatures réelles · {len(cards)} sets</footer>
</body></html>'''
    path = out / "index.html"
    path.write_text(page, encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser(description="galerie de modèles LeoCAD .lcd")
    ap.add_argument("--gallery", metavar="DOSSIER")
    ap.add_argument("--out", default=str(PROJECT / "out" / "web" / "gallery"))
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--sets", default=None,
                    help="liste de sets séparés par des virgules (ex: 0497,6801)")
    args = ap.parse_args()
    if not args.gallery:
        raise SystemExit("usage: lcd.py --gallery DOSSIER [--limit 12]")
    only = [x.strip() for x in args.sets.split(",")] if args.sets else None
    path = gallery(args.gallery, args.out, args.limit, only=only)
    print(path)


if __name__ == "__main__":
    main()
