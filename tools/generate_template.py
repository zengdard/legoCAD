#!/usr/bin/env python3
"""Client text-to-LEGO par templates : prompt -> DeepSeek (paramètres
uniquement) -> géométrie déterministe -> .ldr -> aperçu -> vidéo.

Prérequis : export DEEPSEEK_API_KEY=sk-...
Usage :
    python3 tools/generate_template.py "une maison beige avec un toit rouge"
    python3 tools/generate_template.py "une tour de garde grise" --no-video
    python3 tools/generate_template.py "maison" --params '{"width": 18}'  # sans LLM
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

from ldraw_model import LDrawModel  # noqa: E402
from templates import PARAM_PROMPT, TEMPLATES  # noqa: E402
import render as rend  # noqa: E402


def ask_params(client, prompt: str) -> dict:
    filled = PARAM_PROMPT
    filled = filled.replace("{params_house}", TEMPLATES["house"]["params"])
    filled = filled.replace("{params_tower}", TEMPLATES["tower"]["params"])
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "system", "content": filled},
                  {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.4,
        max_tokens=500,
    )
    return json.loads(resp.choices[0].message.content)


def build_from_params(params: dict) -> LDrawModel:
    ttype = params.pop("type", "house")
    if ttype not in TEMPLATES:
        raise SystemExit(f"Type de template inconnu : {ttype!r} "
                         f"(disponibles : {', '.join(TEMPLATES)})")
    return TEMPLATES[ttype]["build"](params)


def main():
    ap = argparse.ArgumentParser(description="text -> paramètres -> LEGO -> vidéo")
    ap.add_argument("prompt")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--params", default=None,
                    help="JSON de paramètres direct (contourne DeepSeek)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.params:
        params = json.loads(args.params)
        print("Paramètres fournis directement.", flush=True)
    else:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise SystemExit("Définis DEEPSEEK_API_KEY ou utilise --params")
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        print("[1/3] DeepSeek choisit les paramètres...", flush=True)
        params = ask_params(client, args.prompt)
    print(f"      params: {json.dumps(params, ensure_ascii=False)}", flush=True)

    print("[2/3] Génération déterministe de la géométrie...", flush=True)
    model = build_from_params(dict(params))
    # pas de settle() ici : la géométrie des templates est correcte par
    # construction (le toit en plancher est solidaire des murs)
    name = model.name if model.name != "model" else "build"
    name = "".join(c if c.isalnum() else "_" for c in name).strip("_") or "build"
    ldr = PROJECT / "models" / f"{name}.ldr"
    model.save(ldr, comments=args.prompt)
    print(f"      {len(model.bricks)} briques -> {ldr}", flush=True)

    png = PROJECT / "renders" / f"{name}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    print("[3/3] Rendus...", flush=True)
    rend.render_image(ldr, png, lat=30, lon=45)
    result = {"ldr": str(ldr), "preview": str(png),
              "n_bricks": len(model.bricks), "params": params,
              "parts_used": model.parts_summary()}
    if not args.no_video:
        mp4 = rend.build_video(ldr, PROJECT / "renders" / f"{name}.mp4", lat=30)
        result["video"] = str(mp4)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
