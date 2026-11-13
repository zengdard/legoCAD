#!/usr/bin/env python3
"""Serveur web léger (stdlib) : génère un set LEGO complet depuis le navigateur.

    python3 web/server.py --host 127.0.0.1 --port 8000
    # ou : docker compose up

Routes :
    GET  /                     interface
    GET  /api/health           état (LLM configuré, LeoCAD disponible)
    GET  /api/examples         formes de démonstration
    POST /api/generate         {shape|prompt, name, width, llm, video}
    GET  /out/web/<job>/...    .ldr, aperçu, notice.html, BOM, wanted list

Aucune dépendance Python obligatoire (http.server). Le rendu LeoCAD est
optionnel : sans Flatpak/LeoCAD, la notice reste générée sans images.
Une seule génération à la fois (verrou) pour éviter de saturer un petit VPS.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import re
import shutil
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))

WEB = Path(__file__).resolve().parent
OUT = PROJECT / "out" / "web"
LOCK = threading.Lock()
MAX_BODY = 64 * 1024
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")

EXAMPLES = [
    {"id": "house", "label": "Maison", "desc": "Murs, porte, fenêtres, toit et plaque",
     "width": 16},
    {"id": "rocket", "label": "Fusée", "desc": "Corps, nez, ailerons, hublot",
     "width": 26},
    {"id": "car", "label": "Voiture", "desc": "Châssis plein, habitacle, vitres",
     "width": None},
    {"id": "duck", "label": "Canard", "desc": "Forme organique (compilateur)",
     "width": None},
    {"id": "tree", "label": "Sapin", "desc": "Cône constructible + tronc",
     "width": None},
    {"id": "spaceship", "label": "Vaisseau Classic Space",
     "desc": "Gris/bleu, verrière jaune, réacteurs", "width": None},
    {"id": "brick", "label": "Brique géante", "desc": "Le test minimal",
     "width": 4},
]


def _json_response(handler, obj, status=200):
    data = json.dumps(obj, ensure_ascii=False).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(data)


def _unique_name(base: str) -> str:
    base = base.strip() or "modele"
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", base)[:40] or "modele"
    name = base
    n = 2
    while (OUT / name).exists() or (PROJECT / "models" / f"{name}.ldr").exists():
        name = f"{base}-{n}"
        n += 1
    return name


def _has_leocad() -> bool:
    return shutil.which("flatpak") is not None


def generate(payload: dict) -> dict:
    import make_model
    import shapes
    import text_to_voxel

    prompt = str(payload.get("prompt") or "").strip()
    shape = str(payload.get("shape") or "").strip()
    ldr_path = payload.get("ldr_path")
    image_path = payload.get("image_path")
    native = bool(payload.get("native"))
    name = str(payload.get("name") or "").strip()
    width = payload.get("width")
    llm = bool(payload.get("llm", True))
    video = bool(payload.get("video", False))
    if not prompt and not shape and not ldr_path and not image_path:
        raise ValueError("indique une forme, un texte ou un fichier")
    if shape and shape not in shapes.SHAPES:
        raise ValueError(f"forme inconnue : {shape}")
    job = _unique_name(name or (prompt[:30] if prompt else
                                (shape or Path(str(ldr_path or image_path)).stem)))
    source = {"mode": "shape", "shape": shape}
    grid = None
    if ldr_path:
        args = _args(ldr=str(ldr_path), name=job, video=video,
                     ldr_native=native)
        source = {"mode": "ldr", "file": Path(ldr_path).name}
        result = make_model.run(args)
        result["source"] = source
        return _with_files(result, job)
    if image_path:
        args = _args(image=str(image_path), name=job, video=video)
        source = {"mode": "image", "file": Path(image_path).name}
        result = make_model.run(args)
        result["source"] = source
        return _with_files(result, job)
    if prompt:
        use_llm = llm and bool(__import__("os").environ.get("DEEPSEEK_API_KEY")
                               or __import__("os").environ.get("OPENAI_API_KEY"))
        grid, meta = text_to_voxel.generate(prompt, use_llm=use_llm,
                                            name=job, verbose=False)
        source = {"mode": meta.get("mode", "texte"), "prompt": prompt}
        if not use_llm:
            source["note"] = ("Pas de clé LLM : forme choisie par mots-clés. "
                              "Ajoute DEEPSEEK_API_KEY pour le mode texte.")
    if grid is not None:
        vox = OUT / f"_{job}.vox.json"
        vox.parent.mkdir(parents=True, exist_ok=True)
        grid.save(vox)
        args = _args(vox=str(vox), name=job, video=video)
    else:
        args = _args(shape=shape, name=job, width=width, video=video)
    result = make_model.run(args)
    result["source"] = source
    return _with_files(result, job)


def _with_files(result: dict, job: str) -> dict:
    result["files"] = {
        "ldr": f"/out/web/{job}/{Path(result['ldr']).name}",
        "preview": (f"/out/web/{job}/{Path(result['preview']).name}"
                    if result.get("preview") else None),
        "notice": f"/out/web/{job}/notice.html" if result.get("notice") else None,
        "csv": f"/out/web/{job}/{job}.bom.csv",
        "xml": f"/out/web/{job}/{job}.wanted_list.xml",
        "json": f"/out/web/{job}/{job}.bom.json",
    }
    result["job"] = job
    return result


def import_file(payload: dict) -> dict:
    """Fichier .ldr/.mpd ou image envoyé par le navigateur (base64)."""
    import base64
    import uuid

    kind = str(payload.get("kind") or "").lower()
    filename = Path(str(payload.get("filename") or "upload")).name
    raw = str(payload.get("data") or "")
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ValueError("fichier illisible (base64)") from exc
    if not blob or len(blob) > 3 * 1024 * 1024:
        raise ValueError("fichier vide ou trop gros (max 3 Mo)")
    suffix = Path(filename).suffix.lower()
    if kind == "ldr":
        if suffix not in (".ldr", ".mpd"):
            raise ValueError("format attendu : .ldr ou .mpd")
    elif kind == "image":
        if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
            raise ValueError("image attendue : png, jpg, webp")
    else:
        kind = "ldr" if suffix in (".ldr", ".mpd") else "image"
    updir = PROJECT / "out" / "uploads"
    updir.mkdir(parents=True, exist_ok=True)
    path = updir / f"{uuid.uuid4().hex[:12]}{suffix}"
    path.write_bytes(blob)
    name = str(payload.get("name") or Path(filename).stem)
    data = {"name": name, "video": bool(payload.get("video", False)),
            "native": bool(payload.get("native", False))}
    data["ldr_path" if kind == "ldr" else "image_path"] = str(path)
    return generate(data)


def _args(**kw):
    import argparse
    import os
    defaults = dict(shape=None, vox=None, ldr=None, image=None, name=None,
                    width=None, parts_per_step=12, no_tiles=False,
                    stack=False,
                    no_render=bool(os.environ.get("LEGOCAD_NO_RENDER")),
                    no_notice=False,
                    no_notice_render=False, video=False, json=True,
                    ldr_native=False)
    defaults.update(kw)
    return argparse.Namespace(**defaults)


class Handler(BaseHTTPRequestHandler):
    server_version = "legoCAD/2.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send_file(self, path: Path):
        if not path.exists() or not path.is_file():
            self.send_error(404, "fichier introuvable")
            return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        if path in ("/", "/index.html"):
            return self._send_file(WEB / "index.html")
        if path == "/gallery":
            self.send_response(301)
            self.send_header("Location", "/gallery/")
            self.end_headers()
            return
        if path == "/gallery/":
            return self._send_file(OUT / "gallery" / "index.html")
        if path.startswith("/gallery/"):
            target = (OUT / "gallery" / unquote(path[len("/gallery/"):])).resolve()
            try:
                target.relative_to((OUT / "gallery").resolve())
            except ValueError:
                return self.send_error(403, "chemin interdit")
            return self._send_file(target)
        if path == "/api/health":
            import os
            return _json_response(self, {
                "ok": True, "leocad": _has_leocad(),
                "llm": bool(os.environ.get("DEEPSEEK_API_KEY")
                            or os.environ.get("OPENAI_API_KEY")),
                "version": "2.0",
            })
        if path == "/api/examples":
            return _json_response(self, {"examples": EXAMPLES})
        if path.startswith("/out/web/"):
            rel = path[len("/out/web/"):]
            target = (OUT / rel).resolve()
            try:
                target.relative_to(OUT.resolve())
            except ValueError:
                return self.send_error(403, "chemin interdit")
            return self._send_file(target)
        if path.startswith("/static/"):
            target = (WEB / path[len("/static/"):]).resolve()
            try:
                target.relative_to(WEB.resolve())
            except ValueError:
                return self.send_error(403, "chemin interdit")
            return self._send_file(target)
        return self.send_error(404)

    def do_POST(self):
        route = urlparse(self.path).path
        if route not in ("/api/generate", "/api/import"):
            return self.send_error(404)
        length = int(self.headers.get("Content-Length") or 0)
        limit = 4 * 1024 * 1024 if urlparse(self.path).path == "/api/import" \
            else MAX_BODY
        if length <= 0 or length > limit:
            return _json_response(self, {"ok": False,
                                          "error": "requête vide ou trop grosse"},
                                  400)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("JSON attendu")
        except (ValueError, json.JSONDecodeError) as exc:
            return _json_response(self, {"ok": False, "error": str(exc)}, 400)
        if route == "/api/generate":
            # jamais de chemin arbitraire fourni par le client
            payload.pop("ldr_path", None)
            payload.pop("image_path", None)
        if not LOCK.acquire(blocking=False):
            return _json_response(self, {
                "ok": False,
                "error": "une génération est déjà en cours, réessaie dans "
                         "quelques secondes"}, 429)
        try:
            if route == "/api/import":
                result = import_file(payload)
            else:
                result = generate(payload)
            return _json_response(self, {"ok": True, **result})
        except Exception as exc:
            traceback.print_exc()
            return _json_response(self, {"ok": False, "error": str(exc)}, 500)
        finally:
            LOCK.release()


def main():
    ap = argparse.ArgumentParser(description="serveur web legoCAD")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"legoCAD sur http://{args.host}:{args.port}  "
          f"(LeoCAD: {'oui' if _has_leocad() else 'non'})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
