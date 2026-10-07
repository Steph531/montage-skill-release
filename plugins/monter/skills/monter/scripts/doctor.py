#!/usr/bin/env python3
"""doctor.py - vérifie l'environnement du skill et donne la commande exacte pour installer ce qui manque.

Usage : python doctor.py [--fix]
--fix : installe tout seul les dépendances Python (numpy, faster-whisper, opencv).
Les logiciels système (ffmpeg, Node.js) ne sont jamais installés ici : la commande est affichée,
Claude la propose à l'utilisateur et la lance après son accord.
Code de sortie 0 si tout est prêt, 1 sinon.
"""
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OS = platform.system()  # Darwin, Windows, Linux


def have(m):
    return importlib.util.find_spec(m) is not None


def node_major():
    node = shutil.which("node")
    if not node:
        return 0
    v = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip().lstrip("v")
    try:
        return int(v.split(".")[0])
    except ValueError:
        return 0


def system_install(tool):
    """commande d'installation de ffmpeg / node pour ce système, ou un lien si aucun gestionnaire n'est disponible"""
    if OS == "Darwin":
        if shutil.which("brew"):
            return f"brew install {'ffmpeg' if tool == 'ffmpeg' else 'node'}"
        return ("installe Homebrew (https://brew.sh), puis : brew install ffmpeg" if tool == "ffmpeg"
                else "installeur macOS sur https://nodejs.org (version LTS)")
    if OS == "Windows":
        if shutil.which("winget"):
            return ("winget install -e --id Gyan.FFmpeg" if tool == "ffmpeg"
                    else "winget install -e --id OpenJS.NodeJS.LTS") + "   (puis rouvrir le terminal)"
        return "https://www.gyan.dev/ffmpeg/builds/" if tool == "ffmpeg" else "https://nodejs.org (version LTS)"
    # Linux
    if shutil.which("apt-get"):
        return ("sudo apt-get install -y ffmpeg" if tool == "ffmpeg" else
                "curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs")
    if shutil.which("dnf"):
        return "sudo dnf install -y ffmpeg" if tool == "ffmpeg" else "sudo dnf install -y nodejs"
    if shutil.which("pacman"):
        return "sudo pacman -S --noconfirm " + ("ffmpeg" if tool == "ffmpeg" else "nodejs npm")
    return "https://ffmpeg.org/download.html" if tool == "ffmpeg" else "https://nodejs.org"


def main():
    fix = "--fix" in sys.argv
    py_missing = [p for m, p in (("numpy", "numpy"), ("faster_whisper", "faster-whisper"), ("cv2", "opencv"))
                  if not have(m)]
    if fix and py_missing:
        print(f"Installation des dépendances Python : {', '.join(py_missing)}...")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "bootstrap.py"), "--all"])
        importlib.invalidate_caches()
        py_missing = [p for m, p in (("numpy", "numpy"), ("faster_whisper", "faster-whisper"), ("cv2", "opencv"))
                      if not have(m)]

    todo = []  # (élément, commande)
    print(f"Python {platform.python_version()} sur {OS}")
    if sys.version_info < (3, 9):
        todo.append(("Python 3.9+", "winget install -e --id Python.Python.3.12" if OS == "Windows"
                     else "brew install python" if OS == "Darwin" else "sudo apt-get install -y python3"))
    if py_missing:
        todo.append(("dépendances Python (" + ", ".join(py_missing) + ")",
                     f'"{sys.executable}" "{ROOT / "scripts" / "bootstrap.py"}" --all   (ou doctor.py --fix)'))
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        todo.append(("ffmpeg", system_install("ffmpeg")))
    if node_major() < 22:
        todo.append((f"Node.js 22+ (installé : {node_major() or 'aucun'})", system_install("node")))

    if not todo:
        print("Tout est prêt. (Au 1er montage, le modèle de transcription et le navigateur de rendu se téléchargent.)")
        return 0
    print("\nÀ INSTALLER :")
    for what, cmd in todo:
        print(f"  - {what} :\n      {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
