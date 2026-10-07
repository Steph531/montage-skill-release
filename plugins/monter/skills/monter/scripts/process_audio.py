#!/usr/bin/env python3
"""process_audio.py - nettoie des SFX : conversion WAV 48 kHz, coupe silences début/fin,
fondus courts, normalisation de crête. Accepte aiff, wav, mp3, flac, ogg, m4a.

Usage :
    python process_audio.py INPUT [INPUT...] --out library/sfx [--category whoosh]
    python process_audio.py ./mes_sons --out library/sfx --recursive
Les fichiers d'origine ne sont jamais modifiés.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

EXT = {".aif", ".aiff", ".wav", ".mp3", ".flac", ".ogg", ".m4a"}
# seuil de silence (dB) par catégorie : plus bas = on garde les queues naturelles
THRESH = {"whoosh": -62, "riser": -62, "ding": -70, "bass_drop": -65, "pop": -58,
          "click": -55, "glitch": -58, "default": -62}
PEAK_DB = -1.0
# sons dont la montée commence très bas : on ne coupe pas le début
KEEP_START = ("riser", "reverse", "swell", "build")


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def measure_peak(path):
    r = run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
    for ln in r.stderr.splitlines():
        if "max_volume:" in ln:
            return float(ln.split("max_volume:")[1].split("dB")[0])
    return None


def process(src, dst, category, fade_in_ms, fade_out_ms):
    thr = THRESH.get(category, THRESH["default"])
    keep = category in KEEP_START or src.stem.lower().startswith(KEEP_START)
    head = "" if keep else f"silenceremove=start_periods=1:start_threshold={thr}dB:start_silence=0.025,"
    # silenceremove début, puis inversion (areverse) pour couper la fin
    trim = (head +
            f"areverse,"
            f"silenceremove=start_periods=1:start_threshold={thr}dB:start_silence=0.08,"
            f"areverse")
    tmp = dst.with_suffix(".tmp.wav")
    r = run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-af", trim,
             "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(tmp)])
    if r.returncode != 0 or not tmp.exists() or duration(tmp) < 0.02:
        tmp.unlink(missing_ok=True)
        return None, "trim a tout supprimé (son quasi silencieux ?)" if r.returncode == 0 else r.stderr[-200:]
    peak = measure_peak(tmp)
    gain = PEAK_DB - peak if peak is not None else 0.0
    d = duration(tmp)
    fo = min(fade_out_ms / 1000, d / 3)
    af = f"volume={gain:.2f}dB,afade=t=in:d={fade_in_ms/1000:.4f},afade=t=out:st={d - fo:.4f}:d={fo:.4f}"
    r = run(["ffmpeg", "-y", "-hide_banner", "-i", str(tmp), "-af", af,
             "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(dst)])
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        return None, r.stderr[-200:]
    return {"duration": round(duration(dst), 3), "gain_db": round(gain, 2)}, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--category", default="default", help=f"seuil adapté : {', '.join(THRESH)}")
    ap.add_argument("--trim-db", type=float, default=None, help="seuil de coupe (dB), plus bas = garde plus de son (ex -70)")
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--fade-in-ms", type=float, default=2)
    ap.add_argument("--fade-out-ms", type=float, default=15)
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg introuvable (voir doctor.py)")
    files = []
    for i in a.inputs:
        p = Path(i)
        if p.is_dir():
            files += [f for f in (p.rglob("*") if a.recursive else p.glob("*"))
                      if f.suffix.lower() in EXT]
        elif p.suffix.lower() in EXT:
            files.append(p)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    for f in sorted(files):
        cat = a.category if a.category != "default" else next(
            (c for c in THRESH if f.stem.lower().startswith(c)), "default")
        # nom de fichier propre : minuscules, espaces/accents -> underscores
        safe = re.sub(r"[^a-z0-9]+", "_", f.stem.lower()).strip("_")
        dst = out / (safe + ".wav")
        if a.trim_db is not None:
            THRESH[cat] = a.trim_db
        info, err = process(f, dst, cat, a.fade_in_ms, a.fade_out_ms)
        if err:
            print(f"KO  {f.name}: {err}")
        else:
            print(f"OK  {f.name} -> {dst.name}  {info['duration']}s  gain {info['gain_db']:+.1f} dB  [{cat}]")
            report[dst.name] = info
    print(f"\n{len(report)}/{len(files)} fichier(s) traités.")


if __name__ == "__main__":
    main()
