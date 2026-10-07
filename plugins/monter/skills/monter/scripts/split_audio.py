#!/usr/bin/env python3
"""split_audio.py - découpe un long fichier en plusieurs sons aux silences.

Usage : python split_audio.py long.wav --out dossier --prefix whoosh [--silence-db -40] [--min-gap 0.15]
Sort dossier/whoosh_01.wav, whoosh_02.wav... (à repasser ensuite dans process_audio.py)
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix", default=None)
    ap.add_argument("--silence-db", type=float, default=-40)
    ap.add_argument("--min-gap", type=float, default=0.15, help="silence mini entre deux sons (s)")
    ap.add_argument("--ranges", help="découpe manuelle : 0-0.25,0.9-1.22 (secondes), ignore la détection")
    ap.add_argument("--min-len", type=float, default=0.08, help="durée mini d'un son gardé (s)")
    a = ap.parse_args()

    src = Path(a.src)
    if a.ranges:
        segs = [tuple(float(v) for v in r.split("-")) for r in a.ranges.split(",")]
        return write(src, a, segs, pad=0.0)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(src), "-af",
                        f"silencedetect=noise={a.silence_db}dB:d={a.min_gap}", "-f", "null", "-"],
                       capture_output=True, text=True)
    total = None
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    if m:
        total = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    sil, st = [], None
    for ln in r.stderr.splitlines():
        if (x := re.search(r"silence_start: (-?[\d.]+)", ln)):
            st = max(float(x[1]), 0)
        if (x := re.search(r"silence_end: ([\d.]+)", ln)) and st is not None:
            sil.append((st, float(x[1])))
            st = None
    if st is not None and total:
        sil.append((st, total))
    # les sons sont entre les silences
    segs, cur = [], 0.0
    for s0, s1 in sil:
        if s0 - cur >= a.min_len:
            segs.append((cur, s0))
        cur = s1
    if total and total - cur >= a.min_len:
        segs.append((cur, total))
    if not segs:
        sys.exit("Aucun son détecté (essaie --silence-db -50).")
    write(src, a, segs, pad=0.06)


def write(src, a, segs, pad):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    prefix = a.prefix or re.sub(r"[^a-z0-9]+", "_", src.stem.lower()).strip("_")
    for i, (s0, s1) in enumerate(segs, 1):
        s0, s1 = max(s0 - pad, 0), s1 + pad
        dst = out / f"{prefix}_{i:02d}.wav"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s0:.3f}", "-to", f"{s1:.3f}",
                        "-i", str(src), "-c:a", "pcm_s16le", str(dst)])
        print(f"{dst.name}  {s0:7.2f}s -> {s1:7.2f}s  ({s1 - s0:.2f}s)")
    print(f"\n{len(segs)} son(s). Repasse-les dans process_audio.py pour nettoyer/normaliser.")


if __name__ == "__main__":
    main()
