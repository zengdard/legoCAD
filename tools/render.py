#!/usr/bin/env python3
"""Rendu headless d'un modèle LDraw via la CLI de LeoCAD (Flatpak),
puis assemblage en vidéo timelapse + rotation 360° via FFmpeg.

Tous les processus externes sont lancés en mode liste d'arguments,
sans interpréteur de commandes, avec chemins validés.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

LEOCAD_APP_ID = "org.leocad.LeoCAD"
PROJECT = Path(__file__).resolve().parent.parent

# Chemins sûrs : sans méta-caractères, sans retour à la ligne,
# et jamais un nom d'option (tiret initial).
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./ -]+$")


def _safe_path(p) -> str:
    s = str(p)
    if not _SAFE_PATH.match(s) or s.startswith("-"):
        raise ValueError(f"Chemin non sûr refusé : {s!r}")
    return s


def _run(args: list[str]) -> None:
    res = subprocess.run(
        ["flatpak", "run", "--filesystem=host", "org.leocad.LeoCAD", *args],
        capture_output=True, text=True, cwd=PROJECT, timeout=600, shell=False,
    )
    err = "\n".join(
        l for l in res.stderr.splitlines()
        if l and "wl_display" not in l and "qpa.plugin" not in l
        and "canberra" not in l and "gtk-module" not in l
    )
    if res.returncode != 0:
        raise RuntimeError(f"LeoCAD a échoué :\n{err or res.stdout}")


def render_image(ldr: Path, out_png: Path, width=1280, height=960,
                 lat=30, lon=45, last_step=None, auto_frame=True) -> Path:
    args = [str(ldr), "-i", str(out_png), "-w", str(width), "-h", str(height)]
    args += auto_camera(Path(ldr), lat, lon) if auto_frame else \
            ["--camera-angles", str(lat), str(lon), "--shading", "default"]
    if last_step:
        args += ["-f", "1", "-t", str(int(last_step))]
    _run(args)
    return out_png


def count_steps(ldr: Path) -> int:
    """Nombre de steps de construction dans un fichier .ldr."""
    return sum(1 for line in ldr.read_text().splitlines()
               if line.strip().rstrip().lower() == "0 step")


def model_bounds_ldraw(ldr: Path) -> tuple[list[float], list[float]] | None:
    """Boîte englobante du modèle en coordonnées LDraw (min, max), calculée
    à partir des positions et des empreintes réelles des pièces."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ldraw_model import _part_data, _NOMINAL_H

    lo = [float("inf")] * 3
    hi = [float("-inf")] * 3
    found = False
    for line in ldr.read_text().splitlines():
        tok = line.split()
        if not tok or tok[0] != "1" or len(tok) < 15:
            continue
        try:
            cx, cy, cz = (float(tok[2]), float(tok[3]), float(tok[4]))
            rot = (float(tok[5]), float(tok[6]), float(tok[7]),
                   float(tok[8]), float(tok[9]), float(tok[10]),
                   float(tok[11]), float(tok[12]), float(tok[13]))
            part_id = tok[14].replace(".dat", "").lower()
        except ValueError:
            continue
        data = _part_data(part_id)
        if data is None:
            continue
        # demi-empreinte : la matrice indique l'orientation (rot 90 échange x/z)
        sx, sz = data["studs_x"] * 10, data["studs_z"] * 10
        hx = abs(rot[0]) * sx + abs(rot[3]) * sz
        hz = abs(rot[6]) * sx + abs(rot[8]) * sz
        hy = _NOMINAL_H.get(data["kind"], 24) / 2.0
        for v, k in (((cx - hx, cx + hx), 0), ((cy - hy, cy + hy), 1),
                     ((cz - hz, cz + hz), 2)):
            lo[k] = min(lo[k], v[0])
            hi[k] = max(hi[k], v[1])
        found = True
    return (lo, hi) if found else None


def frame_of(ldr: Path) -> tuple[list[float], float] | None:
    """Cadre de caméra (centre LDraw, distance) englobant tout le modèle.
    Calculé une seule fois puis réutilisé : la caméra reste stable pendant
    le timelapse, seul le modèle grandit."""
    import math
    bounds = model_bounds_ldraw(ldr)
    if not bounds:
        return None
    lo, hi = bounds
    center = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    radius = max(1.0, 0.5 * math.dist(lo, hi))
    return center, radius


def camera_args(frame: tuple[list[float], float], lat: float, lon: float,
                fov: float = 30.0) -> list[str]:
    """Arguments LeoCAD pour voir `frame` depuis les angles (lat, lon)."""
    import math
    center, radius = frame
    # distance pour que la sphère englobante tienne dans le champ vertical
    dist = radius / math.sin(math.radians(fov) / 2.0) * 1.05
    la, lo_ = math.radians(lat), math.radians(lon)
    dx = math.cos(la) * math.sin(lo_)
    dy = -math.sin(la)          # LDraw : Y pointe vers le bas
    dz = math.cos(la) * math.cos(lo_)
    pos = (center[0] + dist * dx, center[1] + dist * dy, center[2] + dist * dz)
    return ["--camera-position-ldraw",
            *(f"{v:g}" for v in pos),
            *(f"{v:g}" for v in center),
            "0", "-1", "0",       # up = -Y en LDraw
            "--fov", str(fov)]


def auto_camera(ldr: Path, lat: float, lon: float, fov: float = 30.0
                ) -> list[str]:
    """Arguments de caméra cadrant automatiquement tout le modèle."""
    frame = frame_of(Path(ldr))
    if frame is None:
        return ["--camera-angles", str(lat), str(lon), "--shading", "default"]
    return camera_args(frame, lat, lon, fov)


def render_steps(ldr: Path, out_prefix: Path, width=1280, height=960,
                 lat=30, lon=45, last_step=None, frame=None) -> list[Path]:
    """Une image par step de construction : test01.png, test02.png...
    Le cadre (frame) est celui du modèle final : la caméra ne bouge pas."""
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    n_steps = min(int(last_step or count_steps(ldr)), 255)
    frame = frame or frame_of(Path(ldr))
    cam = camera_args(frame, lat, lon) if frame else \
        ["--camera-angles", str(lat), str(lon), "--shading", "default"]
    args = [str(ldr), "-i", str(out_prefix) + ".png", "-w", str(width),
            "-h", str(height), *cam, "-f", "1", "-t", str(n_steps)]
    _run(args)
    pngs = [p for p in out_prefix.parent.glob(out_prefix.name + "*.png")
            if p.stem[len(out_prefix.name):].isdigit()]
    pngs.sort(key=lambda p: int(p.stem[len(out_prefix.name):]))
    return [p for p in pngs if int(p.stem[len(out_prefix.name):]) <= n_steps]


def render_turntable(ldr: Path, out_dir: Path, n_frames=72, width=1280, height=960,
                     lat=30, last_step=None, frame=None) -> list[Path]:
    """Rotation complète : n_frames images à longitude régulière, même cadre."""
    out_dir.mkdir(parents=True, exist_ok=True)
    frame = frame or frame_of(Path(ldr))
    paths = []
    for i in range(n_frames):
        lon = i * 360 / n_frames
        png = out_dir / f"turn_{i:04d}.png"
        cam = camera_args(frame, lat, lon) if frame else \
            ["--camera-angles", str(lat), f"{lon:g}"]
        args = [str(ldr), "-i", str(png), "-w", str(width), "-h", str(height), *cam]
        if last_step:
            args += ["-f", "1", "-t", str(int(last_step))]
        _run(args)
        paths.append(png)
    return paths


def _ffmpeg(args: list[str]) -> None:
    res = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error"] + args,
        capture_output=True, text=True, shell=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg a échoué :\n{res.stderr}")


def make_timelapse(step_pngs: list[Path], out_mp4: Path,
                   fps=2, hold_last_s=1.5, turntable_pngs: list[Path] | None = None,
                   turntable_fps=12) -> Path:
    """Timelapse : chaque step affiché ~0.5s, puis rotation 360° finale."""
    out_mp4 = Path(out_mp4)
    tmp = out_mp4.parent / "_tl_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("f_*.png"):
        f.unlink()
    n = 0
    for png in step_pngs:
        for _ in range(fps):  # ~0.5 s par step à 2 fps... on duplique pour lisser
            n += 1
            (tmp / f"f_{n:05d}.png").write_bytes(png.read_bytes())
    if turntable_pngs:
        for png in turntable_pngs:
            n += 1
            (tmp / f"f_{n:05d}.png").write_bytes(png.read_bytes())
    total_fps = turntable_fps if turntable_pngs else fps
    _ffmpeg(["-framerate", str(total_fps), "-i", str(tmp / "f_%05d.png"),
             "-vf", f"tpad=stop_mode=clone:stop_duration={hold_last_s}",
             "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "20",
             str(out_mp4)])
    return out_mp4


def build_video(ldr: Path, out_mp4: Path, lat=30, width=1280, height=960,
                turntable=True, last_step=None) -> Path:
    """Pipeline complet : steps + (turntable) -> mp4, cadre stable."""
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    frame = frame_of(Path(ldr))
    steps = render_steps(ldr, out_mp4.parent / ("steps_" + out_mp4.stem),
                         width, height, lat, last_step=last_step, frame=frame)
    turns = None
    if turntable:
        turns = render_turntable(ldr, out_mp4.parent / (out_mp4.stem + "_turn"),
                                 n_frames=72, width=width, height=height,
                                 lat=lat, last_step=last_step, frame=frame)
    return make_timelapse(steps, out_mp4, turntable_pngs=turns)
