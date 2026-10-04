#!/usr/bin/env python3
"""Client text-to-LEGO : prompt texte -> DeepSeek -> spec JSON -> .ldr -> vidéo.

Prérequis : export DEEPSEEK_API_KEY=sk-...
Usage :
    python3 tools/generate.py "une petite maison rouge avec un toit vert"
    python3 tools/generate.py "un vaisseau spatial" --no-video
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

from openai import OpenAI  # noqa: E402

from ldraw_model import CollisionError, LDrawModel, UnknownPartError  # noqa: E402
import render as rend  # noqa: E402

SYSTEM_PROMPT = """Tu es un générateur de modèles LEGO au format LDraw.
On te donne une description en langage naturel. Tu réponds UNIQUEMENT avec un
objet JSON (pas de markdown, pas de texte autour) au format :

{"name": "slug_du_modele", "description": "une ligne",
 "steps": [[{"part": "3001", "x": 0, "z": 0, "y": 0, "color": "4", "rot": 0}, ...], ...]}

Règles strictes :
- "part" : id de pièce EXACT pris dans le catalogue fourni.
- x, z : coordonnées en studs du coin de la pièce (integers >= 0), y : niveau
  vertical en plaques (une brique = 3, une plaque = 1, une tuile = 1).
- color : code couleur LDraw du catalogue (chaîne, ex "4").
- rot : 0 ou 90. Avec rot 90, l'empreinte de la pièce est échangée.
- Les pièces NE doivent JAMAIS se chevaucher : chaque cellule (x,y,z) occupée
  par une pièce est interdite aux suivantes. Empile strictement (y = 3 par
  brique, 1 par plaque/tuile).
- Tu n'es pas limité au catalogue : la bibliothèque LDraw complète est
  accessible (les ids du catalogue ci-dessous sont recommandés et sûrs ;
  tout autre id LDraw numérique est accepté s'il existe).
- Construis du bas vers le haut, par étapes logiques ("steps") : socle, murs,
  étages, toit, détails. 4 à 12 étapes.
- Reste compact : 30 à 200 briques, empreinte au sol <= 24x24 studs.
- Formes reconnaissables et symétriques : murs pleins (pas de grille ajourée),
  toits avec pièces "slope", couleurs cohérentes avec la description.
- Une pièce de W x D studs posée en (x,z) occupe les studs x..x+W-1 et
  z..z+D-1. Les briques d'un même mur doivent donc être espacées EXACTEMENT
  de leur largeur (une "Brick 2 x 4" avec rot 0 avance de 4 en x, de 2 en z ;
  avec rot 90 c'est l'inverse). Recouvrement = rejet.
- Pour le socle, utilise une plaque (3031 = 4x4, 3035 = 4x8, 3811 = baseplate
  32x32 si tu veux un grand terrain ; sinon n'en mets pas).
- Évite les minifigs, roues et pièces Technic (non supportées sur la grille).
- Pas de fenêtres/portes (géométrie non gérée par la grille)."""


def _catalog_brief() -> str:
    from ldraw_model import PARTS
    lines = ["PIECES (id | type | empreinte studs x,z | hauteur en briques) :"]
    for p in PARTS.values():
        lines.append(f"{p['id']} | {p['kind']} | {p['studs_x']:.0f}x{p['studs_z']:.0f} | {p['height_brick_units']:.2f}")
    lines.append("\nCOULEURS (code: nom) : " + ", ".join(
        f"{k}: {v['name']}" for k, v in _colors().items()))
    return "\n".join(lines)


def _colors():
    import json
    c = json.loads((PROJECT / "pieces_catalog.json").read_text())["colors"]
    return {k: v for k, v in c.items() if k not in ("16",)}


_AUTO_OFFSETS = [(dx, dz) for r in (1, 2, 3)
                 for dx in range(-r, r + 1) for dz in range(-r, r + 1)
                 if max(abs(dx), abs(dz)) == r]


def _build_and_check(spec: dict, autofit: bool = True) -> tuple[LDrawModel, list[str]]:
    """Construit le modèle. Avec autofit, une brique en collision est
    repositionnée automatiquement au premier emplacement libre voisin
    (au lieu d'être jetée), ce qui comble les trous des murs."""
    errors: list[str] = []
    moved: list[str] = []
    model = LDrawModel(spec.get("name", "model"))
    for si, step in enumerate(spec.get("steps", [])):
        for b in step:
            x, z, y = int(b["x"]), int(b["z"]), int(b.get("y", 0))
            try:
                model.place(str(b["part"]), x, z, y, str(b.get("color", "4")),
                            int(b.get("rot", 0)))
                continue
            except UnknownPartError as e:
                errors.append(f"step {si+1}: {e}")
                continue
            except CollisionError as e:
                if not autofit:
                    errors.append(f"step {si+1}: {e}")
                    continue
            except ValueError as e:
                errors.append(f"step {si+1}: {e}")
                continue
            # collision : recherche d'un emplacement libre voisin
            placed = False
            for dx, dz in _AUTO_OFFSETS:
                try:
                    model.place(str(b["part"]), x + dx, z + dz, y,
                                str(b.get("color", "4")), int(b.get("rot", 0)))
                    moved.append(f"step {si+1}: {b['part']} ({x},{z}) -> ({x+dx},{z+dz})")
                    placed = True
                    break
                except (CollisionError, ValueError):
                    continue
            if not placed:
                errors.append(f"step {si+1}: {b['part']} rejetée, aucun emplacement libre autour de ({x},{z})")
        model.add_step()
    if moved:
        errors.extend(moved)
    return model, errors


def _repair_pass(client, spec: dict, errors: list[str], prompt: str) -> dict:
    """Renvoie les erreurs de validation à DeepSeek pour qu'il corrige sa spec
    (boucle de feedback type FreeCAD MCP, une seule passe)."""
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _catalog_brief() + "\n\nDESCRIPTION : " + prompt},
            {"role": "assistant", "content": json.dumps(spec)},
            {"role": "user", "content": "Ta spec a été validée par le moteur "
             "géométrique et ces briques ont été REJETÉES (collision ou pièce "
             "inconnue) :\n" + "\n".join(errors[:30]) +
             "\nRenvoie la spec COMPLÈTE corrigée (même format JSON, aucune "
             "brique ne doit chevaucher une autre)."},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=8000,
    )
    return json.loads(resp.choices[0].message.content)


def generate(prompt: str, make_video: bool = True) -> dict:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("Définis DEEPSEEK_API_KEY (export DEEPSEEK_API_KEY=sk-...)")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    print("[1/4] Interrogation de DeepSeek...", flush=True)
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _catalog_brief() + "\n\nDESCRIPTION : " + prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.8,
        max_tokens=8000,
    )
    spec = json.loads(resp.choices[0].message.content)
    print(f"      {sum(len(s) for s in spec.get('steps', []))} briques proposées", flush=True)

    print("[2/4] Construction + validation géométrique...", flush=True)
    model, errors = _build_and_check(spec)
    if errors and len(errors) > 2:
        print(f"      {len(errors)} briques rejetées -> passe de correction DeepSeek", flush=True)
        try:
            spec2 = _repair_pass(client, spec, errors, prompt)
            model2, errors2 = _build_and_check(spec2)
            if len(model2.bricks) > len(model.bricks):
                spec, model, errors = spec2, model2, errors2
        except (json.JSONDecodeError, KeyError) as e:
            print(f"      correction ignorée ({e})", flush=True)
    if len(model.bricks) == 0:
        raise SystemExit("Échec : aucune brique valide générée.\n" + "\n".join(errors[:5]))
    n_moved = model.settle()
    if n_moved:
        print(f"      passe de gravité : {n_moved} briques reposées", flush=True)
    if errors:
        print(f"      {len(errors)} briques rejetées (collisions/pièces inconnues)", flush=True)
    name = "".join(c if c.isalnum() else "_" for c in spec.get("name", "model")).strip("_") or "model"
    ldr = PROJECT / "models" / f"{name}.ldr"
    model.save(ldr, comments=spec.get("description", ""))
    print(f"      {len(model.bricks)} briques posées -> {ldr}", flush=True)

    png = PROJECT / "renders" / f"{name}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    print("[3/4] Rendu de l'aperçu...", flush=True)
    rend.render_image(ldr, png, lat=30, lon=45)

    result = {"ldr": str(ldr), "preview": str(png),
              "n_bricks": len(model.bricks),
              "rejected": errors[:10], "parts_used": model.parts_summary()}

    if make_video:
        print("[4/4] Rendu de la vidéo (timelapse + 360°)...", flush=True)
        mp4 = rend.build_video(ldr, PROJECT / "renders" / f"{name}.mp4", lat=30)
        result["video"] = str(mp4)

    return result


def main():
    ap = argparse.ArgumentParser(description="text -> LEGO -> vidéo")
    ap.add_argument("prompt")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--out", default=None, help="fichier JSON de résultat")
    args = ap.parse_args()
    result = generate(args.prompt, make_video=not args.no_video)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
