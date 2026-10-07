#!/usr/bin/env python3
"""bootstrap.py - installe les dépendances Python du skill (et vérifie ffmpeg).

Usage : python scripts/bootstrap.py [--with-whisper] [--download-model small]
"""
import argparse
import importlib.util
import shutil
import subprocess
import sys

BASE = ["numpy"]
WHISPER = ["faster-whisper"]
FACE = ["opencv-python-headless<5"]  # OpenCV 5 ne fournit plus les détecteurs de visage


def have(mod):
    return importlib.util.find_spec(mod.replace("-", "_")) is not None


def pip_install(pkgs):
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", *pkgs]
    r = subprocess.run(cmd)
    if r.returncode != 0:  # PEP 668 (Linux/Homebrew) : on retente
        r = subprocess.run(cmd + ["--break-system-packages"])
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-whisper", action="store_true", help="installe faster-whisper")
    ap.add_argument("--with-face", action="store_true", help="installe opencv (placement des sous-titres selon le visage)")
    ap.add_argument("--all", action="store_true", help="tout installer (whisper + visage)")
    ap.add_argument("--download-model", metavar="NOM",
                    help="télécharge un modèle whisper (tiny, base, small, medium, turbo)")
    a = ap.parse_args()

    todo = [p for p in BASE if not have(p)]
    if a.with_whisper or a.download_model or a.all:
        todo += [p for p in WHISPER if not have(p)]
    if a.with_face or a.all:
        todo += [p for p in FACE if not have("cv2")]
    if todo:
        print("Installation :", ", ".join(todo))
        if not pip_install(todo):
            sys.exit("Échec de pip install. Lance-le à la main : pip install " + " ".join(todo))
    else:
        print("Dépendances Python déjà présentes.")

    if not shutil.which("node"):
        print("\n[!] Node.js 22+ introuvable (nécessaire pour HyperFrames) : https://nodejs.org")
    if not shutil.which("ffmpeg"):
        print("\n[!] ffmpeg introuvable. Installe-le :\n"
              "    Windows : winget install Gyan.FFmpeg\n"
              "    macOS   : brew install ffmpeg\n"
              "    Linux   : sudo apt install ffmpeg")

    if a.download_model:
        from faster_whisper import WhisperModel
        print(f"Téléchargement du modèle '{a.download_model}' (une seule fois)...")
        WhisperModel(a.download_model, device="cpu", compute_type="int8")
        print("Modèle prêt.")
    print("\nOK. Lance ensuite : python scripts/doctor.py")


if __name__ == "__main__":
    main()
