#!/usr/bin/env python3
"""Depth Anything V2 (ONNX) → carte de profondeur, sans PyTorch.

Le modèle `onnx-community/depth-anything-v2-small` (quantisé, 26 Mo) tourne
avec `onnxruntime` sur CPU. Il produit une profondeur relative ; ce script
la normalise en niveaux de gris (clair = proche) et l'écrit pour
`tools/depth_to_voxel.py`.

    python3 tools/depth_onnx.py photo.jpg depth.png
    python3 tools/depth_to_voxel.py --image photo.jpg \\
        --depth-cmd "python3 tools/depth_onnx.py {image} {depth}" --width 32

Le modèle est téléchargé une fois dans ~/.cache/legocad/ (ou --model).
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache" / "legocad"
MODEL_URL = ("https://huggingface.co/onnx-community/depth-anything-v2-small/"
             "resolve/main/onnx/model_quantized.onnx")
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def ensure_model(path: str | Path | None = None) -> Path:
    path = Path(path) if path else CACHE / "depth-anything-v2-small.onnx"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"téléchargement du modèle ({MODEL_URL})…", file=sys.stderr)
        urllib.request.urlretrieve(MODEL_URL, path)
    return path


def predict(image: str | Path, model: str | Path | None = None,
            size: int = 518) -> np.ndarray:
    """Retourne une carte de profondeur normalisée (0..1, 1 = proche)."""
    import onnxruntime as ort
    path = ensure_model(model)
    img = Image.open(image).convert("RGB")
    w, h = img.size
    resized = img.resize((size, size), Image.BILINEAR)
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    arr = (arr - MEAN) / STD
    x = arr.transpose(2, 0, 1)[None, ...]
    session = ort.InferenceSession(str(path),
                                   providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name
    out = session.run(None, {name: x})[0]
    depth = np.squeeze(out).astype(np.float32)
    # Depth Anything produit une profondeur relative où les grandes valeurs
    # sont proches : on normalise pour que « proche = clair »
    lo, hi = float(depth.min()), float(depth.max())
    depth = (depth - lo) / max(1e-6, hi - lo)
    depth = np.asarray(Image.fromarray((depth * 255).astype(np.uint8))
                       .resize((w, h), Image.BILINEAR))
    return depth.astype(np.float32) / 255.0


def main():
    ap = argparse.ArgumentParser(description="Depth Anything V2 ONNX")
    ap.add_argument("image")
    ap.add_argument("out")
    ap.add_argument("--model", default=None)
    ap.add_argument("--size", type=int, default=518)
    args = ap.parse_args()
    d = predict(args.image, args.model, args.size)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((d * 255).astype(np.uint8)).save(out)
    print(f"{out} ({d.shape[1]}×{d.shape[0]})")


if __name__ == "__main__":
    main()
