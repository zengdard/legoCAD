#!/usr/bin/env python3
"""Nomenclature réelle d'un modèle : pièces × couleurs, exports et contrôle
de disponibilité.

Un modèle « constructible » n'est pas seulement géométriquement valide : il
faut pouvoir **acheter les pièces**. Ce module produit :

  - la liste de courses agrégée (pièce + couleur + quantité) ;
  - un export CSV lisible et un export JSON pour l'API/web ;
  - un export BrickLink XML (wanted list) avec la table de correspondance
    des couleurs LDraw → BrickLink (data/bricklink_colors.json) ;
  - un contrôle de disponibilité : combien de couples pièce/couleur ont déjà
    été observés dans de vrais sets (data/part_colors.json, construit à
    partir du corpus OMR — voir tools/availability.py).

Les numéros de pièces des briques et plaques de base sont identiques chez
LDraw et BrickLink (3001, 3020, 3023…), ce qui rend l'export directement
exploitable. Studio (BrickLink) ouvre par ailleurs le .ldr sans conversion.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, asdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
BL_COLORS_PATH = PROJECT / "data" / "bricklink_colors.json"


@dataclass(frozen=True)
class BomRow:
    part_id: str
    desc: str
    color: str
    color_name: str
    count: int
    kind: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _color_table() -> dict:
    try:
        return json.loads((PROJECT / "pieces_catalog.json").read_text())["colors"]
    except (OSError, ValueError, KeyError):
        return {}


def _bricklink_table() -> dict:
    try:
        return json.loads(BL_COLORS_PATH.read_text())
    except (OSError, ValueError):
        return {}


def build(model) -> list[BomRow]:
    """Agrège les pièces du modèle par (part_id, couleur)."""
    colors = _color_table()
    counts: dict[tuple[str, str], int] = {}
    info: dict[str, dict] = {}
    for b in model.bricks:
        key = (str(b["part_id"]), str(b["color"]))
        counts[key] = counts.get(key, 0) + 1
        if key[0] not in info:
            info[key[0]] = model.part(key[0])
    rows = []
    for (pid, color), n in counts.items():
        p = info[pid]
        rows.append(BomRow(
            part_id=pid, desc=str(p.get("desc", "")), color=color,
            color_name=str(colors.get(color, {}).get("name", color)),
            count=n, kind=str(p.get("kind", ""))))
    rows.sort(key=lambda r: (-r.count, r.part_id, int(r.color)
                             if r.color.isdigit() else 0))
    return rows


def totals(rows: list[BomRow]) -> dict:
    return {
        "parts": sum(r.count for r in rows),
        "types": len({r.part_id for r in rows}),
        "part_colors": len(rows),
        "colors": len({r.color for r in rows}),
    }


def summary_line(rows: list[BomRow]) -> str:
    t = totals(rows)
    return (f"{t['parts']} pièces, {t['types']} types, "
            f"{t['part_colors']} couples pièce/couleur, {t['colors']} couleurs")


def to_csv(rows: list[BomRow]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["part_id", "description", "color_ldraw", "color_name",
                "quantity"])
    for r in rows:
        w.writerow([r.part_id, r.desc, r.color, r.color_name, r.count])
    return buf.getvalue()


def to_rebrickable_csv(rows: list[BomRow]) -> str:
    """CSV simple (part_num, color_name, quantity) importable/éditable."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["part_num", "color_name", "quantity"])
    for r in rows:
        w.writerow([r.part_id, r.color_name, r.count])
    return buf.getvalue()


def to_bricklink_xml(rows: list[BomRow]) -> tuple[str, list]:
    """Wanted list BrickLink. Retourne (xml, couleurs non mappées)."""
    bl = _bricklink_table()
    missing = []
    items = []
    for r in rows:
        info = bl.get(r.color) or bl.get(str(int(r.color))
                                        if r.color.isdigit() else r.color)
        if not info:
            missing.append(f"{r.color} ({r.color_name})")
            continue
        items.append(
            "  <ITEM>\n"
            "    <ITEMTYPE>P</ITEMTYPE>\n"
            f"    <ITEMID>{r.part_id}</ITEMID>\n"
            f"    <COLOR>{info['bricklink_id']}</COLOR>\n"
            f"    <MINQTY>{r.count}</MINQTY>\n"
            "  </ITEM>")
    xml = ("<INVENTORY>\n" + "\n".join(items) + "\n</INVENTORY>\n")
    return xml, sorted(set(missing))


def check_availability(rows: list[BomRow], table: dict | None = None,
                       online: bool = False) -> dict:
    """Part des couples pièce/couleur déjà vus dans de vrais sets.

    `table` = contenu de data/part_colors.json (chargé par défaut). Une
    combinaison absente n'est pas forcément impossible, mais elle est
    signalée : c'est le seul contrôle honnête hors ligne."""
    if table is None:
        try:
            table = json.loads(
                (PROJECT / "data" / "part_colors.json").read_text())
        except (OSError, ValueError):
            return {"checked": False}
    parts = table.get("parts", {})
    part_freq = table.get("part_freq", {})
    color_freq = table.get("color_freq", {})
    observed = plausible = 0
    unknown = []
    for r in rows:
        if parts.get(r.part_id, {}).get(r.color, 0) > 0:
            observed += 1
        elif part_freq.get(r.part_id) and color_freq.get(r.color):
            # pièce connue et couleur connue, mais le couple n'apparaît pas
            # dans l'échantillon : probablement disponible, à vérifier
            plausible += 1
            unknown.append({"part_id": r.part_id, "color": r.color,
                            "color_name": r.color_name, "count": r.count,
                            "confidence": "probable"})
        else:
            unknown.append({"part_id": r.part_id, "color": r.color,
                            "color_name": r.color_name, "count": r.count,
                            "confidence": "faible"})
    total = max(1, len(rows))
    result = {
        "checked": True,
        "source": table.get("meta", {}),
        "combos": len(rows),
        "observed": observed,
        "plausible": plausible,
        "score": round((observed + 0.5 * plausible) / total, 3),
        "strict_score": round(observed / total, 3),
        "unknown": unknown,
    }
    if online:
        try:
            from rebrickable import Rebrickable
            rb = Rebrickable()
            result["online"] = rb.verify_rows(rows)
        except Exception as exc:
            result["online"] = {"checked": False, "reason": str(exc)}
    return result


def piece_mix(rows: list[BomRow]) -> dict:
    total = max(1, sum(r.count for r in rows))
    out: dict[str, float] = {}
    for r in rows:
        out[r.part_id] = out.get(r.part_id, 0.0) + r.count / total
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def mix_similarity(rows: list[BomRow], reference: dict | None = None) -> float:
    """Cosine entre la répartition des pièces du modèle et celle d'un corpus
    de sets réels (data/part_colors.json contient `part_freq`)."""
    if reference is None:
        try:
            reference = json.loads(
                (PROJECT / "data" / "part_colors.json").read_text())
        except (OSError, ValueError):
            return 0.0
    ref = reference.get("part_freq") or {}
    if not ref:
        return 0.0
    total_ref = sum(ref.values()) or 1
    ref = {k: v / total_ref for k, v in ref.items()}
    mine = piece_mix(rows)
    keys = set(mine) | set(ref)
    dot = sum(mine.get(k, 0.0) * ref.get(k, 0.0) for k in keys)
    na = sum(v * v for v in mine.values()) ** 0.5
    nb = sum(v * v for v in ref.values()) ** 0.5
    return round(dot / max(1e-9, na * nb), 3)


def export_all(model, out_dir: str | Path, name: str,
               availability: dict | None = None,
               online: bool = False) -> dict:
    """Écrit bom.csv, bom.json, wanted_list.xml et renvoie le récapitulatif."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = build(model)
    xml, missing = to_bricklink_xml(rows)
    avail = availability if availability is not None else \
        check_availability(rows, online=online)
    meta = {"name": name, **totals(rows),
            "availability": avail,
            "mix_similarity": mix_similarity(rows)}
    (out / f"{name}.bom.csv").write_text(to_csv(rows))
    (out / f"{name}.rebrickable.csv").write_text(to_rebrickable_csv(rows))
    (out / f"{name}.wanted_list.xml").write_text(xml)
    (out / f"{name}.bom.json").write_text(json.dumps(
        {"meta": meta, "rows": [r.as_dict() for r in rows]},
        indent=2, ensure_ascii=False))
    return {"rows": rows, "meta": meta, "unmapped_colors": missing,
            "csv": str(out / f"{name}.bom.csv"),
            "xml": str(out / f"{name}.wanted_list.xml")}


def format_table(rows: list[BomRow], max_rows: int = 200) -> str:
    lines = [f"{'qté':>4}  {'pièce':<8} {'couleur':<22} description"]
    for r in rows[:max_rows]:
        lines.append(f"{r.count:>4}  {r.part_id:<8} "
                     f"{r.color_name:<22} {r.desc}")
    if len(rows) > max_rows:
        lines.append(f"... et {len(rows) - max_rows} autres lignes")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(PROJECT / "tools"))
    from ldraw_model import LDrawModel
    if len(sys.argv) < 2:
        raise SystemExit("usage: bom.py modele.ldr [dossier_sortie]")
    model = LDrawModel(Path(sys.argv[1]).stem)
    # recharger le .ldr dans le modèle
    import voxel
    grid = voxel.from_ldr(sys.argv[1])
    from brickify import brickify
    model, _ = brickify(grid, Path(sys.argv[1]).stem)
    rows = build(model)
    print(format_table(rows))
    print(summary_line(rows))
    print(check_availability(rows))
