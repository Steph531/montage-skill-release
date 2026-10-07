#!/usr/bin/env python3
"""face_zones.py - détecte le visage et calcule où placer sous-titres et cards sans le masquer.

Dépendances : opencv-python-headless (détecteur Haar fourni avec le paquet, aucun modèle à télécharger).
Usage : python face_zones.py video.mp4 --out face_zones.json [--fps 4]
        python face_zones.py image.png                      (test sur une image)

Sortie :
{ "width":1080, "height":1920, "face": {"x":..,"y":..,"w":..,"h":..} | null,   # médiane sur la vidéo
  "caption_box": {"x","y","w","h","anchor":"below_face|above_face|bottom"},     # zone sûre pour les sous-titres
  "overlay_zones": [{"name":"left|right|top","x","y","w","h"}],                 # zones libres pour cards/logos
  "samples": [{"t":0.0,"face":{...}|null}], "moves": bool }
Les marges d'interface TikTok/Reels/Shorts sont évitées (bas ~20 %, haut ~8 %, droite ~12 %).
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

import cv2

SAFE_TOP, SAFE_BOTTOM, SAFE_SIDE_R, SAFE_SIDE_L = 0.08, 0.20, 0.12, 0.05


def detector():
    d = cv2.data.haarcascades
    return [cv2.CascadeClassifier(d + "haarcascade_frontalface_default.xml"),
            cv2.CascadeClassifier(d + "haarcascade_profileface.xml")]


def find_face(gray, cascades):
    h, w = gray.shape
    scale = 640 / max(w, h) if max(w, h) > 640 else 1.0
    g = cv2.resize(gray, None, fx=scale, fy=scale) if scale != 1.0 else gray
    g = cv2.equalizeHist(g)
    best = None
    for c in cascades:
        for img, flipped in ((g, False), (cv2.flip(g, 1), True)) if c is cascades[1] else ((g, False),):
            faces = c.detectMultiScale(img, 1.1, 5, minSize=(int(min(g.shape) * 0.08),) * 2)
            for (x, y, fw, fh) in faces:
                if flipped:
                    x = g.shape[1] - x - fw
                if best is None or fw * fh > best[2] * best[3]:
                    best = (x, y, fw, fh)
        if best:
            break
    if not best:
        return None
    x, y, fw, fh = (v / scale for v in best)
    # le détecteur Haar donne le visage strict : on élargit un peu (front, menton, cheveux)
    return {"x": int(x - fw * 0.1), "y": int(y - fh * 0.25), "w": int(fw * 1.2), "h": int(fh * 1.45)}


def zones(face, W, H):
    top, bot = int(H * SAFE_TOP), int(H * (1 - SAFE_BOTTOM))
    left, right = int(W * SAFE_SIDE_L), int(W * (1 - SAFE_SIDE_R))
    cap_h = int(H * 0.16)
    box = {"x": left, "w": right - left, "h": cap_h}
    if face is None:
        box.update(y=int(H * 0.62), anchor="bottom")
        return box, []
    fb = face["y"] + face["h"]
    if bot - fb >= cap_h + int(H * 0.02):          # assez de place sous le menton
        box.update(y=min(fb + int(H * 0.03), bot - cap_h), anchor="below_face")
    elif face["y"] - top >= cap_h + int(H * 0.02):  # sinon au-dessus de la tête
        box.update(y=max(face["y"] - cap_h - int(H * 0.02), top), anchor="above_face")
    else:                                            # visage plein cadre : bas de l'écran sûr
        box.update(y=bot - cap_h, anchor="bottom")
    ov = []
    gap = int(W * 0.03)
    lw, rw = face["x"] - gap - left, right - (face["x"] + face["w"] + gap)
    if lw > W * 0.2:
        ov.append({"name": "left", "x": left, "y": top, "w": lw, "h": bot - top})
    if rw > W * 0.2:
        ov.append({"name": "right", "x": face["x"] + face["w"] + gap, "y": top, "w": rw, "h": bot - top})
    if face["y"] - top > H * 0.12:
        ov.append({"name": "top", "x": left, "y": top, "w": right - left, "h": face["y"] - top - gap})
    return box, ov


def median_face(faces):
    fs = [f for f in faces if f]
    if not fs:
        return None
    return {k: int(statistics.median(f[k] for f in fs)) for k in ("x", "y", "w", "h")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("--out", default="face_zones.json")
    ap.add_argument("--fps", type=float, default=4, help="images analysées par seconde")
    a = ap.parse_args()
    casc = detector()
    p = Path(a.media)
    samples, W, H = [], 0, 0
    if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        img = cv2.imread(str(p))
        if img is None:
            sys.exit("Image illisible")
        H, W = img.shape[:2]
        samples = [{"t": 0.0, "face": find_face(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), casc)}]
    else:
        cap = cv2.VideoCapture(str(p))
        if not cap.isOpened():
            sys.exit("Vidéo illisible")
        W, H = int(cap.get(3)), int(cap.get(4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(int(round(fps / a.fps)), 1)
        i = 0
        while True:
            ok = cap.grab()
            if not ok:
                break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    samples.append({"t": round(i / fps, 2),
                                    "face": find_face(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), casc)})
            i += 1
        cap.release()
    face = median_face([s["face"] for s in samples])
    found = sum(1 for s in samples if s["face"])
    caption, overlays = zones(face, W, H)
    xs = [s["face"]["x"] + s["face"]["w"] / 2 for s in samples if s["face"]]
    moves = bool(xs) and (max(xs) - min(xs)) > W * 0.15
    out = {"width": W, "height": H, "face": face, "caption_box": caption, "overlay_zones": overlays,
           "detection_rate": round(found / max(len(samples), 1), 2), "moves": moves, "samples": samples}
    Path(a.out).write_text(json.dumps(out, indent=2), "utf-8")
    print(f"{W}x{H}  visage détecté sur {found}/{len(samples)} images")
    print("visage :", face)
    print("sous-titres :", caption)
    for z in overlays:
        print("zone libre :", z)
    if found / max(len(samples), 1) < 0.5:
        print("[!] détection faible : éclairage, visage de profil ou trop petit ? Les sous-titres tombent par défaut en bas sûr.")
    if moves:
        print("[i] le visage bouge beaucoup : prévoir une zone de sous-titres fixe plutôt que suiveuse.")


if __name__ == "__main__":
    main()
