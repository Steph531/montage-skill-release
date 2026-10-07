#!/usr/bin/env python3
"""package.py - fabrique ce qu'on distribue : uniquement les fichiers suivis par git (le skill),
sans les vidéos, les montages ni les fichiers de travail (voir aussi export-ignore dans .gitattributes).

Usage :
  python scripts/package.py [dossier_de_sortie]      monter.zip seul (défaut : ~/Desktop)
  python scripts/package.py --release <dossier>      <dossier>/repo (contenu du dépôt public :
                                                     marketplace + plugin) et <dossier>/monter.zip
Le zip contient un dossier « monter/ » prêt à placer dans ~/.claude/skills/.
Version : 1.0.<nombre de commits> (identique dans le zip, plugin.json et marketplace.json).
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def git(*args, binary=False):
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                          text=not binary, check=True).stdout


def make_zip(out_dir):
    out = out_dir / "monter.zip"
    git("archive", "--format=zip", "--prefix=monter/", "-o", str(out), "HEAD")
    return out


def make_release_tree(repo, version):
    if repo.exists():
        shutil.rmtree(repo)
    skill = repo / "plugins" / "monter" / "skills" / "monter"
    skill.mkdir(parents=True)
    subprocess.run(["tar", "-x", "-C", str(skill)], input=git("archive", "--format=tar", "HEAD", binary=True),
                   check=True)

    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    for plugin in marketplace["plugins"]:
        plugin["version"] = version
    (repo / ".claude-plugin").mkdir()
    (repo / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    entry = marketplace["plugins"][0]
    manifest = {"name": entry["name"], "version": version, "description": entry["description"],
                "author": marketplace["owner"]}
    (skill.parent.parent / ".claude-plugin").mkdir()
    (skill.parent.parent / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for name in ("README.md", "CREDITS.md"):
        shutil.copy(skill / name, repo / name)


dirty = git("status", "--porcelain", "--untracked-files=no").strip()
if dirty:
    print("[!] Modifications non commitées : elles ne seront PAS empaquetées (seul le dernier commit l'est).")
version = f"1.0.{git('rev-list', '--count', 'HEAD').strip()}"
rev = git("rev-parse", "--short", "HEAD").strip()

release = len(sys.argv) > 2 and sys.argv[1] == "--release"
if release:
    out_dir = Path(sys.argv[2]).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    make_release_tree(out_dir / "repo", version)
    print(f"{out_dir / 'repo'}  (marketplace, version {version})")
else:
    out_dir = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else Path.home() / "Desktop"
zip_path = make_zip(out_dir)
print(f"{zip_path}  ({zip_path.stat().st_size / 1e6:.1f} Mo, version {version}, {rev})")
if release and "GITHUB_OUTPUT" in os.environ:  # pour la GitHub Action
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"version={version}\n")
