#!/usr/bin/env python3
"""Texte → volume LEGO : le LLM écrit un petit programme, pas des briques.

C'est l'approche « structure-as-code » (cf. BrickWright, 2026) : un agent
codeur est bien meilleur pour décrire une forme avec des primitives que pour
placer 300 briques une par une. Le LLM produit un script Python qui utilise
`VoxelGrid` (boîte, ellipsoïde, cylindre, cône, miroir, peinture) ; le script
est exécuté dans un sous-processus borné, validé, puis compilé en briques
par `brickify`.

    export DEEPSEEK_API_KEY=sk-...
    python3 tools/text_to_voxel.py "un château avec deux tours" --out models/chateau.vox.json
    python3 tools/text_to_voxel.py "une fusée" --no-llm     # heuristique locale

Sans clé API, un classifieur de mots-clés choisit une forme de démonstration
(maison, fusée, canard, voiture, arbre) : le pipeline reste utilisable hors
ligne, et l'utilisateur peut toujours fournir un .vox.json.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

import shapes                          # noqa: E402
from voxel import VoxelGrid            # noqa: E402

MAX_ROUNDS = 4
TIMEOUT_S = 30

SYSTEM = """Tu es un modeleur LEGO. Tu écris un court script Python qui décrit
un VOLUME en voxels ; un compilateur le transforme ensuite en briques réelles.
Tu ne places jamais de briques toi-même.

API disponible (aucun import) :
  g = VoxelGrid()
  g.box(x, y, z, w, h, d, color)          # pavé plein, y en plaques
  g.ellipsoid(cx, cy, cz, rx, ry, rz, color, hollow=0)
  g.cylinder(cx, cz, y0, y1, r, color, hollow=0)
  g.cone(cx, cz, y0, y1, r0, r1, color)   # rayon r0 en bas -> r1 en haut
  g.mirror_x(at=None)   g.translate(dx,dy,dz)   g.normalize()
  g.paint_box(x,y,z,w,h,d,color)          # repeint les voxels existants
  g.erase(x,y,z,w,h,d)   g.shell(thickness=1)   g.clean_colors()
  math (sin, cos, pi, hypot…)

Unités : 1 voxel = 1 stud × 1 plaque (1 brique = 3 plaques). x/z en studs,
y en plaques. Le sol est y=0. Couleurs (codes LDraw) : 0 noir, 1 bleu,
2 vert, 4 rouge, 14 jaune, 15 blanc, 19 tan, 25 orange, 27 lime,
70 marron, 71 gris clair, 72 gris foncé, 320 rouge foncé, 272 bleu foncé,
288 vert foncé, 84 nougat.

Contraintes :
- le volume doit être PLEIN et stable : pas de fine aile dans le vide ;
  les formes s'élargissent vers le bas (une sphère sur un socle, un cône
  posé au sol…), pas vers le haut ;
- maximum 48 studs de large et 60 plaques de haut ; reste simple ;
- définis `def build():` et `return g.normalize()`.

Exemple pour « une petite fusée rouge et blanche » :
```python
def build():
    g = VoxelGrid()
    g.cylinder(5, 5, 0, 18, 4, 15)          # corps blanc
    g.cone(5, 5, 18, 26, 4, 0.5, 4)         # nez rouge
    g.box(1, 0, 4, 3, 8, 3, 4)              # aileron
    g.box(8, 0, 4, 3, 8, 3, 4)
    g.paint_box(3, 11, 1, 5, 4, 1, 43)      # hublot
    return g.normalize()
```

Réponds UNIQUEMENT avec le bloc de code Python."""


def _client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("pip install openai pour le mode LLM") from exc
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY / OPENAI_API_KEY manquante")
    base = os.environ.get("LEGOCAD_LLM_BASE") or (
        "https://api.deepseek.com" if os.environ.get("DEEPSEEK_API_KEY")
        else None)
    return OpenAI(api_key=key, base_url=base) if base else OpenAI(api_key=key)


def _ask(client, messages: list[dict], vision: bool = False) -> str:
    model = os.environ.get(
        "LEGOCAD_VISION_MODEL" if vision else "LEGOCAD_LLM_MODEL",
        "gpt-4o" if vision else "deepseek-chat")
    resp = client.chat.completions.create(
        model=model, messages=messages, temperature=0.4, max_tokens=1800)
    return resp.choices[0].message.content or ""


def _user_message(prompt: str, reference: str | None) -> dict:
    """Message utilisateur, avec l'image de référence si fournie (vision)."""
    if not reference:
        return {"role": "user", "content": prompt}
    import base64
    from pathlib import Path
    p = Path(reference)
    suffix = p.suffix.lower().lstrip(".") or "png"
    mime = "jpeg" if suffix in ("jpg", "jpeg") else suffix
    data = base64.b64encode(p.read_bytes()).decode()
    return {"role": "user", "content": [
        {"type": "text", "text": prompt + "\n\nLa photo jointe est une "
         "référence de STYLE et de proportions (un vrai set Classic Space). "
         "Ne la copie pas : construis un volume original qui s'en inspire."},
        {"type": "image_url",
         "image_url": {"url": f"data:image/{mime};base64,{data}"}},
    ]}


def extract_code(text: str) -> str:
    blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, re.S)
    code = blocks[0] if blocks else text
    return code.strip()


def run_code(code: str, name: str = "script") -> dict:
    """Exécute le script dans un sous-processus (spec → résultat JSON)."""
    spec = PROJECT / "out" / "_voxel_spec.json"
    res = PROJECT / "out" / "_voxel_result.json"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(json.dumps({"name": name, "code": code}))
    res.unlink(missing_ok=True)
    try:
        subprocess.run(["python3", "tools/voxel_runner.py", str(spec),
                        str(res)], capture_output=True, text=True,
                       cwd=str(PROJECT), timeout=TIMEOUT_S, shell=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"Timeout ({TIMEOUT_S} s)"}
    if not res.exists():
        return {"ok": False, "error": "le runner a échoué"}
    return json.loads(res.read_text())


def heuristic(prompt: str) -> VoxelGrid:
    """Repli hors ligne : mots-clés → forme de démonstration."""
    p = prompt.lower()
    table = [
        (("vaisseau", "spaceship", "classic space", "navette"), "spaceship"),
        (("fus", "rocket"), "rocket"),
        (("canard", "duck", "oiseau"), "duck"),
        (("voiture", "car", "camion", "truck", "bus"), "car"),
        (("arbre", "sapin", "tree", "forêt", "foret"), "tree"),
        (("maison", "house", "chalet", "cabane", "château", "chateau"), "house"),
    ]
    for words, shape in table:
        if any(w in p for w in words):
            return shapes.make(shape)
    return shapes.make("house")


def generate(prompt: str, use_llm: bool = True, name: str = "model",
             verbose: bool = True,
             reference: str | None = None) -> tuple[VoxelGrid, dict]:
    """Texte → (grille, métadonnées). Boucle de correction sur erreur."""
    if not use_llm:
        return heuristic(prompt), {"mode": "heuristique", "rounds": 0}
    client = _client()
    messages = [
        {"role": "system", "content": SYSTEM},
        _user_message(prompt, reference),
    ]
    last_error = ""
    for round_no in range(1, MAX_ROUNDS + 1):
        try:
            text = _ask(client, messages, vision=bool(reference))
        except Exception as exc:
            if reference:
                # le modèle texte ne gère pas les images : on repart sans
                messages[1] = {"role": "user", "content": prompt}
                reference = None
                text = _ask(client, messages, vision=False)
            else:
                raise
        code = extract_code(text)
        if verbose:
            print(f"[tour {round_no}] script de {len(code.splitlines())} lignes",
                  flush=True)
        res = run_code(code, name)
        if res.get("ok"):
            grid = VoxelGrid.from_dict(res["grid"])
            return grid, {"mode": "llm", "rounds": round_no, "code": code,
                          "stats": res.get("stats")}
        last_error = str(res.get("error"))
        if verbose:
            print(f"[tour {round_no}] erreur : {last_error}", flush=True)
        messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content":
             "Le script a échoué : " + last_error +
             "\nCorrige-le et renvoie le code complet."},
        ]
    # dernier recours : heuristique, mais on signale l'échec du LLM
    return heuristic(prompt), {"mode": "heuristique-apres-erreur",
                               "rounds": MAX_ROUNDS, "error": last_error}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="texte → volume LEGO → briques")
    ap.add_argument("prompt")
    ap.add_argument("--out", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--bricks", action="store_true",
                    help="compiler aussi en .ldr + notice")
    ap.add_argument("--reference", default=None,
                    help="image de référence (vision) pour guider le volume")
    args = ap.parse_args()
    name = args.name or "modele"
    grid, meta = generate(args.prompt, use_llm=not args.no_llm, name=name,
                          reference=args.reference)
    out = Path(args.out) if args.out else \
        PROJECT / "models" / f"{name}.vox.json"
    grid.save(out)
    print(f"volume : {out} ({grid.count()} voxels, {grid.size()})")
    if args.bricks:
        import make_model
        argv = ["--vox", str(out), "--name", name]
        import argparse as _ap
        ns = _ap.Namespace(shape=None, image=None, ldr=None, vox=str(out),
                           name=name, width=None, parts_per_step=12,
                           no_tiles=False, stack=False, no_render=False,
                           no_notice=False, no_notice_render=False,
                           video=False, json=True)
        result = make_model.run(ns)
        print(json.dumps({k: result[k] for k in ("ldr", "preview", "notice",
                                                "score")}, indent=2,
                         ensure_ascii=False))
    else:
        print(json.dumps(meta, indent=2, ensure_ascii=False)[:800])


if __name__ == "__main__":
    main()
