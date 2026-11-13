#!/usr/bin/env python3
"""Notice PDF via LPub3D (headless), avec repli sur la notice HTML.

LPub3D est le seul outil de notice LEGO réellement headless : il lit les
métacommandes `0 !LPUB ...` et produit des pages avec callouts, BOM et
vues par étape. Il n'est pas installé par défaut.

    flatpak install flathub io.github.trevorsandy.LPub3D
    python3 tools/pdf_notice.py models/maison.ldr --out out/maison.pdf

Sans LPub3D, `make_model --pdf` conserve `notice.html` (imprimable en PDF
depuis le navigateur) et affiche un message.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
APP = "io.github.trevorsandy.LPub3D"


def available() -> bool:
    try:
        res = subprocess.run(["flatpak", "list", "--app", "--columns=application"],
                             capture_output=True, text=True, timeout=20)
        return APP in res.stdout.split()
    except Exception:
        return False


def build(ldr: str | Path, out_pdf: str | Path, timeout: int = 900) -> Path:
    """Génère un PDF ; lève RuntimeError si LPub3D est absent/échoue."""
    if not available():
        raise RuntimeError(
            "LPub3D absent : installe io.github.trevorsandy.LPub3D "
            "(flatpak) ou imprime notice.html en PDF depuis le navigateur")
    ldr = Path(ldr).resolve()
    out = Path(out_pdf).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        ["flatpak", "run", "--filesystem=host", APP,
         "-pe", "-o", "pdf", "-of", str(out),
         "-od", str(out.parent), str(ldr)],
        cwd=str(PROJECT), capture_output=True, text=True, timeout=timeout,
        shell=False)
    if res.returncode != 0 or not out.exists():
        err = "\n".join(l for l in res.stderr.splitlines()
                        if "Gtk-Message" not in l and "qpa.plugin" not in l)
        raise RuntimeError(f"LPub3D a échoué :\n{err or res.stdout}")
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="notice PDF via LPub3D")
    ap.add_argument("ldr")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not available():
        raise SystemExit("LPub3D n'est pas installé (flatpak). "
                         "Utilise notice.html ou installe-le.")
    out = Path(args.out) if args.out else \
        Path(args.ldr).with_suffix(".pdf")
    print(build(args.ldr, out))


if __name__ == "__main__":
    main()
