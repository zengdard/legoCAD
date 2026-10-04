#!/usr/bin/env python3
"""Bibliothèque de « construction patterns » (le LLM choisit le pattern
conceptuel, le solver choisit les briques concrètes).

Chaque variante définit les pièces autorisées PAR NIVEAU de briques :
  - cheap      : toutes les longueurs autorisées, le solver converge vers
                 les briques longues (moins de pièces) ;
  - strong     : alternate des longueurs d'un niveau sur l'autre pour
                 décaler les joints verticaux (appareillage de maçon) ;
  - decorative : comme strong, avec alternance de couleurs gérée par
                 lego_ir._colors_per_level.

Les plates (h=1) restent toujours autorisées : elles servent à tomber
exactement sur la hauteur demandée.
"""
from __future__ import annotations

VARIANTS = ("cheap", "strong", "decorative")

# part ids sûrs (catalogue curé) : briques 1xN / 2xN et plates 1xN / 2xN
BRICKS_1 = {"1": "3005", "2": "3004", "3": "3622", "4": "3010",
            "6": "3009", "8": "3008"}
BRICKS_2 = {"2": "3003", "3": "3002", "4": "3001"}
PLATES_1 = {"1": "3024", "2": "3023", "3": "3623", "4": "3710"}
PLATES_2 = {"2": "3022", "3": "3021", "4": "3020"}

# appareillage « strong » : longueurs alternées d'un niveau de brique à l'autre
STRONG_A = ("2", "4")
STRONG_B = ("2", "3", "6")


def part_mix(pattern: str, depth2: bool, level_plate: int = 0) -> dict:
    """{(largeur studs, hauteur plaques): [part_id]} autorisées à ce niveau.

    level_plate sert uniquement à l'appareillage « strong » : les niveaux
    pairs (en briques) utilisent STRONG_A, les impairs STRONG_B.
    """
    odd = (level_plate // 3) % 2 == 1
    if pattern == "strong" and odd:
        lens = STRONG_B
    elif pattern == "strong":
        lens = STRONG_A
    else:
        lens = tuple(BRICKS_1)

    mix = {(1, 3): [BRICKS_1[l] for l in lens],
           (1, 1): list(PLATES_1.values())}
    if depth2:
        if pattern == "strong":
            lens2 = ("2", "4") if not odd else ("2", "3")
        else:
            lens2 = tuple(BRICKS_2)
        mix[(2, 3)] = [BRICKS_2[l] for l in lens2]
        mix[(2, 1)] = list(PLATES_2.values())
    return mix


def describe() -> str:
    """Résumé pour le prompt LLM (choix du pattern conceptuel)."""
    return ("- pattern \"cheap\" : moins de pièces (briques longues), "
            "joints alignés\n"
            "- pattern \"strong\" : joints décalés niveau par niveau "
            "(mur d'appareillage, plus solide)\n"
            "- pattern \"decorative\" : comme strong, avec bandes de "
            "couleur alternées (blanc/taupe)")
