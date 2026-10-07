#!/usr/bin/env python3
"""derush.py - dérushage automatique : retire les prises ratées, les bégaiements et les blancs.

Usage : python derush.py transcript.json --out edit.json [--cut P02 P07] [--restore P03]

Principe :
1. Les mots sont regroupés en phrases (ponctuation forte, fin de segment whisper, pause > 0.7 s).
2. Une phrase est une prise ratée si on la retrouve presque entière (>= 70 % des mots) dans une
   des 10 phrases suivantes : on garde toujours la dernière prise. Les phrases gardées non terminées
   par un point sont ensuite fusionnées avec la suivante (une phrase = une idée).
3. Les répétitions immédiates (« c'est c'est ») sont retirées.
4. Les coupes sont calées sur l'énergie du son (--audio) : début 40 ms avant la parole, fin juste
   après la chute du volume ; les blancs intérieurs de plus de 0,3 s sont retirés.
5. Chaque segment dure un nombre entier d'images (pas de dérive audio/vidéo).

Sortie edit.json :
{ "segments": [{"src_start","src_end","out_start"}],   # morceaux de la source gardés, dans l'ordre
  "duration": 61.4,                                    # durée finale
  "phrases": [{"id":"P01","text","kept":bool,"reason","src_start","src_end","start","end"}],
  "words":   [{"word","start","end","phrase"}] }        # mots gardés, temps de la vidéo finale
"""
import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

PHRASE_GAP = 0.7      # pause qui sépare deux phrases (s)
RETAKE_WINDOW = 10    # une reprise arrive dans les 10 phrases suivantes (les blancs de rush peuvent être longs)
RETAKE_COVER = 0.7    # part des mots retrouvés dans la prise suivante
PAD_IN, PAD_OUT = 0.08, 0.15
KEEP_PAUSE = 0.15     # respiration gardée quand on coupe un blanc
MIN_SEG = 0.12
RUN_GAP = 0.4         # écart entre deux mots au-delà duquel on recoupe (le son entre eux n'est pas transcrit)
TAIL = 0.4            # vidéo gardée après le dernier mot (au-delà, on se relâche face caméra) ; plan.tail
# écart max entre une séquence et sa répétition : un mot répété après une longue pause peut être voulu,
# une suite de 3 mots et plus répétée après une pause est un faux départ
STUTTER_GAP = {1: 0.6, 2: 2.0, 3: 8.0}
MAX_WORD = 1.0        # un mot plus long est un horodatage gonflé par whisper (il couvre du son non transcrit)
FILLERS = {"euh", "heu", "hum", "bah", "uh", "um", "erm"}


def norm_word(w):
    w = unicodedata.normalize("NFD", w.lower())
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", w)


def stem(w):
    return w[:5]


def split_phrases(segments):
    phrases, cur = [], []
    for s in segments:
        for w in s.get("words", []):
            if cur and w["start"] - cur[-1]["end"] > PHRASE_GAP:
                phrases.append(cur)
                cur = []
            cur.append(w)
            if re.search(r"[.?!…]$", w["word"].strip()):
                phrases.append(cur)
                cur = []
        if cur:  # fin de segment whisper
            phrases.append(cur)
            cur = []
    return [p for p in phrases if p]


def tokens(p):
    return [stem(t) for t in (norm_word(w["word"]) for w in p) if t and t not in FILLERS]


def coverage(a, b):
    """part des mots de a retrouvés, dans l'ordre, dans b"""
    if not a:
        return 0.0
    m = SequenceMatcher(None, a, b, autojunk=False)
    return sum(blk.size for blk in m.get_matching_blocks()) / len(a)


def detect_retakes(phrases):
    toks = [tokens(p) for p in phrases]
    reasons = [None] * len(phrases)
    for i, p in enumerate(phrases):
        if all(norm_word(w["word"]) in FILLERS or not norm_word(w["word"]) for w in p):
            reasons[i] = "hésitation"
            continue
        if len(toks[i]) < 3:
            continue
        for j in range(i + 1, min(i + 1 + RETAKE_WINDOW, len(phrases))):
            # la reprise peut s'étaler sur 2 phrases consécutives
            later = toks[j] + (toks[j + 1] if j + 1 < len(toks) else [])
            if coverage(toks[i], later) >= RETAKE_COVER:
                reasons[i] = f"reprise (refaite plus loin)"
                break
    return reasons


def spoken(ws):
    """une répétition à durée quasi nulle est un doublon inventé par whisper, pas un bégaiement"""
    return ws[-1]["end"] - ws[0]["start"] >= 0.12


def stutter_cuts(words):
    """indices des mots à retirer : séquence de 1 à 6 mots répétée immédiatement"""
    t = [norm_word(w["word"]) for w in words]
    drop, phantom, i = set(), set(), 0
    while i < len(words):
        for k in (6, 5, 4, 3, 2, 1):
            if i + 2 * k <= len(words) and all(t[i:i + k]) and t[i:i + k] == t[i + k:i + 2 * k] \
                    and words[i + k]["start"] - words[i + k - 1]["end"] < STUTTER_GAP[min(k, 3)] \
                    and spoken(words[i:i + k]):
                if spoken(words[i + k:i + 2 * k]):
                    drop.update(range(i, i + k))       # vrai bégaiement : on coupe la 1re occurrence
                else:
                    phantom.update(range(i + k, i + 2 * k))  # doublon whisper : hors sous-titres seulement
                i += k - 1
                break
        if t[i] in FILLERS:
            drop.add(i)
        i += 1
    return drop, phantom


def subtract(intervals, holes):
    out = []
    for a, b in intervals:
        cur = a
        for h0, h1 in holes:
            if h1 <= cur or h0 >= b:
                continue
            # on garde un peu de respiration de chaque côté du blanc
            cut0, cut1 = h0 + KEEP_PAUSE / 2, h1 - KEEP_PAUSE / 2
            if cut1 - cut0 <= 0:
                continue
            if cut0 > cur:
                out.append((cur, cut0))
            cur = max(cur, cut1)
        if b > cur:
            out.append((cur, b))
    return [(a, b) for a, b in out if b - a >= MIN_SEG]


class Energy:
    """volume du son par tranches de 10 ms + masque parole/silence. Les horodatages de whisper sont
    imprécis de 100 à 300 ms (pire après un long blanc) : ils disent seulement où chercher,
    la coupe tombe dans le silence réel le plus proche."""
    HOP = 0.01

    def __init__(self, wav):
        import wave
        import numpy as np
        with wave.open(str(wav)) as f:
            sr, ch = f.getframerate(), f.getnchannels()
            x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if ch > 1:
            x = x.reshape(-1, ch).mean(1)
        hop = int(sr * self.HOP)
        n = len(x) // hop
        db = 10 * np.log10((x[:n * hop].reshape(n, hop) ** 2).mean(1) + 1e-10)
        floor, peak = np.percentile(db, 10), np.percentile(db, 95)
        self.thr = floor + max(10.0, 0.4 * (peak - floor))  # au-dessus des souffles
        m = list(db > self.thr)
        m = _fill(m, True, 8)    # trous < 80 ms dans la parole : c'est encore de la parole
        m = _fill(m, False, 3)   # pics isolés < 30 ms : bruit
        self.db, self.m = db.tolist(), m

    def i(self, t):
        return int(min(max(round(t / self.HOP), 0), len(self.m) - 1))

    def local_min(self, t0, t1):
        i0, i1 = self.i(t0), self.i(t1)
        k = min(range(i0, max(i1, i0) + 1), key=lambda k: self.db[k])
        return k * self.HOP

    def snap_start(self, t, lo):
        """début de coupe : 40 ms avant que la parole démarre"""
        m, it = self.m, self.i(t)
        if m[it]:
            # parole déjà en cours à l'horodatage : whisper est en retard. Si rien n'a été dit juste
            # avant (mot précédent loin), on remonte jusqu'au vrai début du son (jusqu'à 1 s)
            back = 1.0 if t - lo > 0.6 else 0.15
            j, stop = it, self.i(max(lo + 0.05, t - back))
            while j > stop and m[j - 1]:
                j -= 1
            if j > stop:
                return max(j * self.HOP - 0.04, lo, 0)
            return max(self.local_min(max(lo - 0.1, t - 0.15), t + 0.05), 0)
        j, lim = it, self.i(t + 0.3)  # horodatage dans le blanc : whisper en avance
        while j < lim and not m[j]:
            j += 1
        return max((j if m[j] else it) * self.HOP - 0.04, lo, 0)

    def snap_end(self, t, hi, wstart):
        """fin de coupe : juste après la chute du volume (+60 ms pour la fin de la consonne)"""
        m, it = self.m, self.i(t)
        if not m[it]:  # horodatage gonflé sur le blanc : on remonte jusqu'au dernier son
            j = it
            while j > self.i(wstart) and not m[j]:
                j -= 1
            off = j
        else:
            fwd = 0.6 if hi - t > 0.6 else 0.3
            j, lim = it, self.i(min(hi - 0.05, t + fwd))
            while j < lim and m[j]:
                j += 1
            if m[j]:  # parole continue avec le mot suivant (retiré) : point le plus calme autour de la
                # frontière ; fenêtre large car l'horodatage du mot suivant est aussi imprécis
                return self.local_min(t - 0.05, t + 0.15)
            off = j - 1
        return min(off * self.HOP + 0.06, max(hi, off * self.HOP))

    def speech_ratio(self, a, b):
        i0, i1 = self.i(a), self.i(b)
        return sum(self.m[i0:i1 + 1]) / max(i1 - i0 + 1, 1)

    def silences(self, a, b, min_len=0.3):
        """blancs de plus de min_len s entre a et b"""
        out, k, i1 = [], self.i(a), self.i(b)
        while k <= i1:
            if not self.m[k]:
                j = k
                while j <= i1 and not self.m[j]:
                    j += 1
                if (j - k) * self.HOP >= min_len:
                    out.append((k * self.HOP, j * self.HOP))
                k = j
            k += 1
        return out


def _fill(m, value, max_len):
    """remplace par value les suites de (not value) plus courtes que max_len, entourées de value"""
    out, k = list(m), 0
    while k < len(out):
        if out[k] != value:
            j = k
            while j < len(out) and out[j] != value:
                j += 1
            if 0 < k and j < len(out) and j - k < max_len:
                out[k:j] = [value] * (j - k)
            k = j
        k += 1
    return out


def trim_cuts(stream, trims):
    """indices des mots retirés par plan.trim : de `from` à `to` inclus dans la phrase `at`
    (début de mot, `n` = n-ième occurrence de `from`) ; renvoie aussi les erreurs"""
    drop, errors = set(), []
    for t in trims:
        idx = [k for k, (_, pid) in enumerate(stream) if pid == t["at"]]
        if not idx:
            errors.append(f"trim {t['at']} : phrase absente du montage")
            continue
        def find(kw, after, nth=1):
            kw = norm_word(kw)
            for k in idx:
                if k >= after and kw and norm_word(stream[k][0]["word"]).startswith(kw):
                    nth -= 1
                    if not nth:
                        return k
        a = find(t["from"], idx[0], t.get("n", 1))
        b = find(t["to"], a) if a is not None else None
        if b is None:
            errors.append(f"trim {t['at']} : «{t['from']}»…«{t['to']}» introuvable")
            continue
        drop.update(range(a, b + 1))
    return drop, errors


# textes que whisper invente sur le bruit ou le silence (génériques de sous-titres vus à l'entraînement)
HALLUCINATIONS = [r"sous ?titres? (realises|faits?) par (la communaute )?(d ?|l ?)?amara( org)?", r"(la communaute )?(d ?|l ?)?amara org",
                  r"sous ?titrage [a-z]{0,4} ?\d+", r"sous ?titrage (st|fr|societe radio canada)",
                  r"merci d ?avoir regarde( cette video)?", r"sous ?titres? par [a-z ]{0,30}"]


def mark_hallucinations(tr):
    """marque (w["hallu"]) les mots qui forment un de ces textes inventés ; ils ne sont pas supprimés pour que la
    numérotation des phrases (P01, P02…) ne bouge pas quand la liste HALLUCINATIONS évolue"""
    for seg in tr["segments"]:
        ws = seg.get("words", [])
        if not ws:
            continue
        txt, span = "", []
        for k, w in enumerate(ws):
            n = norm_word(w["word"])
            if n:
                if txt:
                    txt += " "
                span.append((len(txt), len(txt) + len(n), k))
                txt += n
        bad = set()
        for pat in HALLUCINATIONS:
            for m in re.finditer(pat, txt):
                bad |= {k for a, b, k in span if a < m.end() and b > m.start()}
        for k in bad:
            ws[k]["hallu"] = True


def build(tr, cut=(), restore=(), audio=None, fps=30, trim=(), tail=TAIL, head=0.0, intro=None, cold=None):
    mark_hallucinations(tr)
    for seg in tr["segments"]:
        for w in seg.get("words", []):
            if w["end"] - w["start"] > MAX_WORD:
                w["start"] = round(w["end"] - 0.6, 3)
    # numérotation sur la transcription complète (stable), puis on retire les mots inventés de chaque phrase
    atoms = split_phrases(tr["segments"])
    invented = [all(w.get("hallu") for w in a) for a in atoms]
    atoms = [a if inv else [w for w in a if not w.get("hallu")] for a, inv in zip(atoms, invented)]
    # détection des reprises sur les seules phrases réelles (une phrase inventée ne doit pas occuper la fenêtre de comparaison)
    real = [i for i, inv in enumerate(invented) if not inv]
    found = dict(zip(real, detect_retakes([atoms[i] for i in real])))
    reasons = [found.get(i, "texte inventé (whisper)") for i in range(len(atoms))]
    for i in range(len(atoms)):
        if f"P{i + 1:02d}" in restore:
            reasons[i] = None
    # fusion : une phrase gardée non terminée continue dans la phrase gardée suivante
    phrases, pr = [], []
    for i, p in enumerate(atoms):
        if not reasons[i] and phrases and not pr[-1] and not re.search(r"[.?!…]$", phrases[-1][-1]["word"].strip()):
            phrases[-1] = phrases[-1] + p
            continue
        phrases.append(list(p))
        pr.append(reasons[i])
    reasons = pr
    ids, n = [], 0
    for p in phrases:  # id = numéro de la première phrase d'origine (stable entre deux passes)
        n = next(k for k, a in enumerate(atoms) if a[0] is p[0])
        ids.append(f"P{n + 1:02d}")
    for i, pid in enumerate(ids):
        if pid in cut:
            reasons[i] = "coupé à la main"

    stream = [(w, ids[i]) for i, p in enumerate(phrases) if not reasons[i] for w in p]
    drop, phantom = stutter_cuts([w for w, _ in stream])
    tdrop, trim_errors = trim_cuts(stream, trim)
    drop |= tdrop
    kept_words = [x for k, x in enumerate(stream) if k not in drop]
    phantom_ids = {id(stream[k][0]) for k in phantom}

    # intervalles source : une suite de mots consécutifs dans la source (aucun mot retiré entre eux)
    allw = [w for seg in tr["segments"] for w in seg.get("words", [])]
    pos = {id(w): k for k, w in enumerate(allw)}
    runs = []
    for w, _ in kept_words:
        if runs and pos[id(w)] == pos[id(runs[-1][-1])] + 1 and w["start"] - runs[-1][-1]["end"] < RUN_GAP:
            runs[-1].append(w)
        else:
            runs.append([w])
    energy = Energy(audio) if audio and Path(audio).exists() else None
    intervals = []
    for r in runs:
        k0, k1 = pos[id(r[0])], pos[id(r[-1])]
        lo = min(allw[k0 - 1]["end"], r[0]["start"] - 0.05) if k0 > 0 else 0.0
        hi = allw[k1 + 1]["start"] if k1 + 1 < len(allw) else (tr.get("duration") or r[-1]["end"] + 1)
        if energy:
            a = energy.snap_start(r[0]["start"], lo)
            b = energy.snap_end(r[-1]["end"], hi, r[-1]["start"])
            if energy.speech_ratio(a, b) < 0.25:
                continue  # quasi pas de voix à cet endroit : mot mal horodaté par whisper, ignoré
            holes = energy.silences(a, b)
            cur = a
            for h0, h1 in holes:  # blanc intérieur : on garde 80 ms après la voix, 40 ms avant
                c0, c1 = h0 + 0.08, h1 - 0.04
                if c1 - c0 >= 0.15:
                    intervals.append((cur, c0))
                    cur = c1
            intervals.append((cur, b))
        else:  # sans audio : horodatages whisper + blancs ffmpeg (moins précis)
            intervals += subtract([(max(r[0]["start"] - PAD_IN, lo), min(r[-1]["end"] + PAD_OUT, hi))],
                                  [(x["start"], x["end"]) for x in tr.get("silences", [])])
    intervals = [(a, b) for a, b in intervals if b - a >= MIN_SEG]

    if intervals and head:  # hook visuel avant le premier mot (main devant l'objectif, entrée dans le cadre…)
        intervals[0] = (max(0.0, intervals[0][0] - head), intervals[0][1])
    if intervals and intro:  # hook visuel pris ailleurs dans la source (ex : entrée dans le cadre avant un faux départ)
        intervals.insert(0, (float(intro[0]), float(intro[1])))
    # flash-forward (hook) : un passage fort d'une phrase gardée, rejoué en ouverture ; il reste aussi à sa place
    cold_words, errors_cold = [], []
    if intervals and cold:
        k = next((i for i, pid in enumerate(ids) if pid == cold.get("at")), None)
        pw = phrases[k] if k is not None else []
        def find(kw, after=0):
            kw = norm_word(kw)
            return next((j for j in range(after, len(pw)) if kw and norm_word(pw[j]["word"]).startswith(kw)), None)
        a = find(cold.get("from", "")) if pw else None
        b = find(cold.get("to", ""), a or 0) if a is not None else None
        if b is None:
            errors_cold.append(f"cold_open {cold.get('at')} : «{cold.get('from')}»…«{cold.get('to')}» introuvable")
        else:
            cold_words = pw[a:b + 1]
            # après le geste filmé s'il y en a un (le geste joué reste la toute première image)
            intervals.insert(1 if intro else 0, (max(0.0, cold_words[0]["start"] - 0.06), cold_words[-1]["end"] + 0.15))
    if intervals:  # queue : on laisse respirer la fin, sans dépasser la source
        src_end = tr.get("duration") or intervals[-1][1]
        intervals[-1] = (intervals[-1][0], min(intervals[-1][1] + tail, src_end))
    # durées en nombre entier d'images : audio et vidéo sont coupés sur la même grille,
    # sinon les arrondis s'additionnent et la bouche se décale au fil des coupes
    segs, frames = [], 0
    for k, (a, b) in enumerate(intervals):
        n = round((b - a) * fps)
        if n < 3:
            continue
        segs.append({"src_start": round(a, 4), "src_end": round(a + n / fps, 4),
                     "frames": n, "out_start": round(frames / fps, 4),
                     **({"cold": True} if cold_words and k == (1 if intro else 0) else {})})
        frames += n
    t = frames / fps

    def remap(x, in_cold=False):  # le passage du flash-forward existe deux fois : on choisit lequel
        for s in segs:
            if bool(s.get("cold")) == in_cold and s["src_start"] - 1e-6 <= x <= s["src_end"] + 1e-6:
                return round(s["out_start"] + x - s["src_start"], 3)
        return None

    words = []
    for w, pid in kept_words:
        if id(w) in phantom_ids:
            continue
        st = remap(w["start"])
        if st is None:  # début du mot tombé dans un blanc coupé : on prend le début du segment suivant
            st = next((s["out_start"] for s in segs if not s.get("cold") and s["src_start"] >= w["start"]), None)
            if st is None:
                continue
        en = remap(min(w["end"], w["start"] + 1.0)) or st + 0.3
        words.append({"word": w["word"], "start": st, "end": round(max(en, st + 0.05), 3), "phrase": pid})

    for w in cold_words:  # sous-titres du flash-forward (phrase « COLD »)
        st = remap(w["start"], True)
        if st is not None:
            en = remap(min(w["end"], w["start"] + 1.0), True) or st + 0.3
            words.append({"word": w["word"], "start": st, "end": round(max(en, st + 0.05), 3), "phrase": "COLD"})
    words.sort(key=lambda w: w["start"])

    voice_db = None
    if energy:  # niveau habituel de la voix : sert à repérer les phrases murmurées (apartés)
        sp = sorted(d for d, m in zip(energy.db, energy.m) if m)
        voice_db = sp[len(sp) // 2] if sp else None

    def quiet(p):
        if voice_db is None:
            return False
        i0, i1 = energy.i(p[0]["start"]), energy.i(p[-1]["end"])
        loud = sorted(energy.db[i0:i1 + 1])[-max((i1 - i0) // 5, 1):]  # 20 % les plus forts
        return bool(loud) and sum(loud) / len(loud) < voice_db - 6

    out_phrases = []
    for i, p in enumerate(phrases):
        pw = [w for w in words if w["phrase"] == ids[i]]
        out_phrases.append({
            "id": ids[i], "text": "".join(
                (w["word"] if w["word"][:1] in "-'" else " " + w["word"]) for w in p).strip(),
            "kept": not reasons[i], "reason": reasons[i], "quiet": quiet(p),
            "src_start": p[0]["start"], "src_end": p[-1]["end"],
            "start": pw[0]["start"] if pw else None, "end": pw[-1]["end"] if pw else None})
    return {"segments": segs, "duration": round(t, 4), "frames": frames, "fps": fps,
            "phrases": out_phrases, "words": words, "errors": trim_errors + errors_cold,
            "cold_end": next((x["out_start"] + x["frames"] / fps for x in segs if x.get("cold")), None)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--out", default="edit.json")
    ap.add_argument("--cut", nargs="*", default=[])
    ap.add_argument("--restore", nargs="*", default=[])
    ap.add_argument("--audio", help="WAV de la source : cale les coupes sur l'énergie du son")
    a = ap.parse_args()
    tr = json.loads(Path(a.transcript).read_text("utf-8"))
    ed = build(tr, a.cut, a.restore, a.audio)
    Path(a.out).write_text(json.dumps(ed, ensure_ascii=False, indent=1), "utf-8")
    src = tr.get("duration") or 0
    print(f"{src:.1f}s -> {ed['duration']:.1f}s, {len(ed['segments'])} coupe(s) -> {a.out}")
    for p in ed["phrases"]:
        print(f"{'  ' if p['kept'] else '~ '}{p['id']} {p['text'][:70]}" + (f"   [{p['reason']}]" if p['reason'] else ""))


if __name__ == "__main__":
    main()
