#!/usr/bin/env python3
"""index_library.py - construit/maj library/manifest.json à partir des fichiers présents.
Pour chaque fichier : nom, catégorie (déduite du préfixe), durée, et champs de licence
à remplir : source_url, author, license. Les valeurs déjà saisies sont conservées.

Usage : python index_library.py [--check]
--check : sort en erreur si un fichier n'a pas de licence renseignée (avant de partager !)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library"
MANIFEST = LIB / "manifest.json"
TAXO = ROOT / "taxonomy.json"
EMBEDDABLE = {"CC0", "OWN"}  # redistribuables sans condition
KNOWN = EMBEDDABLE | {"CC-BY", "CC-BY-NC", "OTHER"}
EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".png", ".svg", ".webp", ".jpg", ".mp4", ".webm", ".mov"}


def dur(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=nw=1:nk=1", str(p)], capture_output=True, text=True)
        return round(float(r.stdout.strip()), 3)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    taxo = json.loads(TAXO.read_text("utf-8"))["sounds"] if TAXO.exists() else {}
    old = {}
    if MANIFEST.exists():
        old = {e["file"]: e for e in json.loads(MANIFEST.read_text("utf-8"))["assets"]}
    assets = []
    for kind in ("sfx", "music", "broll", "icons"):
        d = LIB / kind
        for f in sorted(d.rglob("*")) if d.exists() else []:
            if not f.is_file() or f.suffix.lower() not in EXT:
                continue
            rel = f.relative_to(LIB).as_posix()
            e = old.get(rel, {})
            parts = f.relative_to(LIB / kind).parts
            cat = parts[0] if len(parts) > 1 else (f.stem.rsplit("_", 1)[0] if f.stem[-2:].isdigit() else f.stem)
            t = taxo.get(f.relative_to(LIB / kind).with_suffix("").as_posix(), {})
            assets.append({
                "file": rel, "type": kind, "category": e.get("category", cat),
                "duration": dur(f) if f.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".mp4", ".webm", ".mov"} else None,
                "source_url": e.get("source_url", ""), "author": e.get("author", ""),
                "license": e.get("license", ""), "source": e.get("source", ""),
                "role": t.get("role", e.get("role", "")), "intensity": t.get("intensity", e.get("intensity")),
                "tags": t.get("tags", e.get("tags", [])),
            })
    MANIFEST.write_text(json.dumps({"assets": assets}, ensure_ascii=False, indent=2), "utf-8")
    missing = [x["file"] for x in assets if x["license"] not in KNOWN]
    non_free = [x["file"] for x in assets if x["license"] in {"CC-BY-NC", "OTHER"}]
    needs_credit = [x["file"] for x in assets if x["license"] == "CC-BY"]
    print(f"{len(assets)} asset(s) indexé(s) -> {MANIFEST.relative_to(ROOT)}")
    if missing:
        print(f"[!] {len(missing)} sans licence valide (CC0 / OWN / CC-BY / CC-BY-NC / OTHER) :")
        for m in missing[:15]:
            print("    ", m)
    if non_free:
        print(f"[!] {len(non_free)} non redistribuable(s) tel quel (NC/OTHER) : à retirer avant partage.")
    if needs_credit:
        print(f"[i] {len(needs_credit)} en CC-BY : auteur + URL obligatoires dans CREDITS.md.")
    if a.check and (missing or non_free):
        sys.exit(1)


if __name__ == "__main__":
    main()
