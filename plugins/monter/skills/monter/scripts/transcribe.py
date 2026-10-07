#!/usr/bin/env python3
"""transcribe.py - transcription mot par mot + détection des silences (faster-whisper).

Usage :
    python transcribe.py video.mp4 --lang fr --out transcript.json
    python transcribe.py video.mp4 --model turbo --device cuda
Le modèle est téléchargé automatiquement au premier lancement (Hugging Face).

Sortie transcript.json :
{ "language": "fr", "duration": 61.2,
  "segments": [{"start":0.0,"end":3.1,"text":"...","words":[{"word":"Salut","start":0.1,"end":0.5,"prob":0.98}]}],
  "silences": [{"start":3.1,"end":3.9,"duration":0.8}] }
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def extract_audio(src, dst):
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vn",
                        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)])
    if r.returncode != 0:
        sys.exit("Extraction audio impossible (fichier sans piste audio ?)")


def find_silences(audio, thr_db, min_dur):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(audio), "-af",
                        f"silencedetect=noise={thr_db}dB:d={min_dur}", "-f", "null", "-"],
                       capture_output=True, text=True)
    out, start = [], None
    for ln in r.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", ln)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", ln)
        if m and start is not None:
            out.append({"start": round(start, 3), "end": round(float(m.group(1)), 3),
                        "duration": round(float(m.group(2)), 3)})
            start = None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("--lang", default=None, help="fr, en... (auto si absent)")
    ap.add_argument("--model", default="small", help="tiny/base/small/medium/turbo (multilingues)")
    ap.add_argument("--device", default="auto", help="auto/cpu/cuda")
    ap.add_argument("--compute-type", default=None, help="int8 (CPU) / float16 (GPU)")
    ap.add_argument("--out", default="transcript.json")
    ap.add_argument("--silence-db", type=float, default=-35)
    ap.add_argument("--silence-min", type=float, default=0.4)
    ap.add_argument("--keep-audio", help="garde l'audio 16 kHz mono extrait à ce chemin (WAV)")
    a = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg introuvable (python scripts/doctor.py)")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("faster-whisper manquant : python scripts/bootstrap.py --with-whisper")

    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        extract_audio(a.media, wav)
        if a.keep_audio:
            shutil.copy(wav, a.keep_audio)
        silences = find_silences(wav, a.silence_db, a.silence_min)
        ct = a.compute_type or ("float16" if a.device == "cuda" else "int8")
        print(f"Chargement du modèle '{a.model}' ({a.device}, {ct})...")
        model = WhisperModel(a.model, device=a.device, compute_type=ct)
        lang = a.lang
        if not lang:  # détection seule (le générateur n'est pas consommé) pour choisir le prompt
            lang = model.transcribe(str(wav), vad_filter=True)[1].language
        # transcription passage par passage (entre deux blancs) : d'un seul tenant, whisper fusionne
        # les prises successives d'une même phrase et en saute certaines, qui passent alors au montage
        import wave
        import numpy as np
        with wave.open(str(wav)) as wf:
            sr = wf.getframerate()
            audio = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768
        total = len(audio) / sr
        regions, t = [], 0.0
        for x in silences:
            if x["start"] - t > 0.15:
                regions.append((t, x["start"]))
            t = max(t, x["end"])
        if total - t > 0.15:
            regions.append((t, total))
        out = {"language": lang, "duration": round(total, 3), "segments": [], "silences": silences}
        for r0, r1 in regions:
            off = max(r0 - 0.1, 0)
            chunk = audio[int(off * sr):int((r1 + 0.1) * sr)]
            segs, _ = model.transcribe(chunk, language=lang, word_timestamps=True,
                                       condition_on_previous_text=False, vad_filter=False)
            for s in segs:
                if s.no_speech_prob > 0.6 and s.avg_logprob < -1:
                    continue  # bruit pris pour de la parole
                words = [{"word": w.word.strip(), "start": round(off + w.start, 3),
                          "end": round(off + w.end, 3), "prob": round(w.probability, 3)}
                         for w in (s.words or []) if w.word.strip()]
                if not words:
                    continue
                out["segments"].append({"start": words[0]["start"], "end": words[-1]["end"],
                                        "text": s.text.strip(), "words": words})
                print(f"[{words[0]['start']:6.1f}s] {s.text.strip()}")
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), "utf-8")
    print(f"\n{len(out['segments'])} segment(s), {len(silences)} silence(s) -> {a.out}")


if __name__ == "__main__":
    main()
