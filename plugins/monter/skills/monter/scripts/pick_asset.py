#!/usr/bin/env python3
"""pick_asset.py - choisit un son de la bibliothèque selon le besoin.

Exemples :
    python pick_asset.py --category transitions --intensity 1
    python pick_asset.py --tag whoosh --max-intensity 2 --avoid pop_01 pop_02
    python pick_asset.py --category ui --tag appear --seed 3 --json
    python pick_asset.py --list                      # tout ce qui existe
Sort le chemin du fichier (ou un JSON avec --json). Le choix est pseudo-aléatoire :
--avoid permet de ne pas répéter les derniers sons utilisés.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "library" / "manifest.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", help="dossier : transitions, ui, impacts, tension, reaction, business, divers")
    ap.add_argument("--tag", help="un tag : whoosh, pop, riser, cash...")
    ap.add_argument("--intensity", type=int, help="intensité exacte (1-3)")
    ap.add_argument("--max-intensity", type=int, help="intensité maximale")
    ap.add_argument("--avoid", nargs="*", default=[], help="noms (sans extension) à ne pas reprendre")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--type", default="sfx", help="sfx, music, broll, icons")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    if not MANIFEST.exists():
        sys.exit("manifest.json absent : lance python scripts/index_library.py")
    items = [x for x in json.loads(MANIFEST.read_text("utf-8"))["assets"] if x["type"] == a.type]

    def ok(x):
        if a.category and x["category"] != a.category:
            return False
        if a.tag and a.tag.lower() not in [t.lower() for t in x.get("tags", [])]:
            return False
        i = x.get("intensity")
        if a.intensity is not None and i != a.intensity:
            return False
        if a.max_intensity is not None and (i or 0) > a.max_intensity:
            return False
        return True

    found = [x for x in items if ok(x)]
    if a.list:
        for x in found:
            print(f"{x['file']:38s} i{x.get('intensity')}  {x.get('duration')}s  {x.get('role', '')}")
        return
    pool = [x for x in found if Path(x["file"]).stem not in set(a.avoid)] or found
    if not pool:
        sys.exit("Aucun son ne correspond. Essaie sans --tag/--intensity, ou --list.")
    pick = random.Random(a.seed).choice(pool)
    pick = dict(pick, path=str((ROOT / "library" / pick["file"]).resolve()))
    print(json.dumps(pick, ensure_ascii=False) if a.json else pick["path"])


if __name__ == "__main__":
    main()
