#!/usr/bin/env python3
"""pipeline.py - montage complet d'une vidéo courte. Tout ce qui est mécanique est ici ;
Claude n'intervient que pour écrire plan.json (quels effets, à quels moments).

    python pipeline.py prepare video.mp4 [--lang fr] [--model small]
        -> .montage/<nom>/ : transcription, visage, dérushage, suggestions (plan.auto.json)
           et brief.txt, le résumé compact que Claude lit pour écrire plan.json
    python pipeline.py render .montage/<nom> [--draft] [--auto]
        -> output/<nom>_monte.mp4 (travail dans .montage/<nom>/)  (--auto : utilise plan.auto.json sans relecture)
    python pipeline.py auto video.mp4 [--draft]
        -> prepare + render --auto d'un coup (aucune décision de Claude)
    python pipeline.py verify .montage/<nom>
        -> retranscrit le montage et liste les mots amputés aux coupes

Format de plan.json (voir SKILL.md) :
{ "cut": ["P04"], "restore": [],
  "events": [{"at": "P13", "word": "sans", "fx": "check", "text": "Sans abonnement"}, ...] }
"""
import argparse
import json
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import derush  # noqa: E402

STRIKE_AT = 0.7  # s après l'apparition d'un screen barré (strike) : le trait rouge commence à se tracer
STRIKE_DRAW = 0.28  # durée du tracé : l'impact (son) tombe quand le trait a fini de barrer
LIST_HOLD = 1.8  # s : la liste reste affichée après son dernier point
STEP_HOLD = 2.0  # s : une scène / maquette à étapes reste affichée après sa dernière étape (le temps de l'animation)
LIST_SCALE = 0.56  # taille de la vidéo réduite par défaut (calée en bas, panneau au-dessus)
LIST_SCALE_MIN, LIST_SCALE_MAX = 0.5, 0.7  # bornes de la réduction adaptée au contenu
VOICE_NORM = "loudnorm=I=-14:TP=-1.5:LRA=11"

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "engine"
HYPERFRAMES = "hyperframes@0.8.119"  # version testée, figée : une mise à jour ne casse pas le skill
FPS = 30
CAP_SIZE = 80
OVERLAY_FX = {"card", "check", "cross", "stat", "emoji", "cta", "flash", "timer", "list", "screen", "chart", "title", "number", "percent", "hook", "icon", "splash", "blob", "scene", "diagram", "site"}


def log(msg):
    print(msg, flush=True)


def die(msg):
    sys.exit(f"[x] {msg}")


def run(cmd, label, quiet=True, timeout=None):
    try:
        r = subprocess.run([str(c) for c in cmd], capture_output=quiet, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        die(f"{label} s'est figé (plus de {timeout:.0f} s) : la machine est sans doute surchargée (autres rendus, appli "
            f"gourmande, mode économie d'énergie). Ferme ce qui tourne et relance la même commande.")
    if r.returncode != 0:
        tail = "\n".join(((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-25:])
        die(f"{label} a échoué :\n{tail}")
    return r


def load(p, default=None):
    p = Path(p)
    return json.loads(p.read_text("utf-8")) if p.exists() else default


def save(p, data):
    Path(p).write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


def probe(video):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height:stream_side_data=rotation:format=duration", "-of", "json", video], "ffprobe")
    d = json.loads(r.stdout)
    s = d["streams"][0]
    w, h = s["width"], s["height"]
    rot = next((abs(int(x.get("rotation", 0))) for x in s.get("side_data_list", []) if "rotation" in x), 0)
    if rot in (90, 270):
        w, h = h, w
    return w, h, float(d["format"]["duration"])


def out_size(w, h):
    if h > w:
        return 1080, 1920
    if w > h:
        return 1920, 1080
    return 1080, 1080


def check_env():
    missing = [x for x in ("ffmpeg", "ffprobe", "node", "npx") if not shutil.which(x)]
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        missing.append("faster-whisper (python scripts/bootstrap.py --all)")
    if missing:
        die("Il manque : " + ", ".join(missing) + f"\nLance : python \"{ROOT / 'scripts' / 'doctor.py'}\" --fix "
            "(installe les dépendances Python et donne la commande pour le reste)")


# ---------------------------------------------------------------- suggestions automatiques

def toks(s):
    return [t for t in (derush.norm_word(x) for x in re.split(r"[\s'’\-]+", s)) if t]


def display_words(words):
    """fusionne les morceaux whisper (« sous » + « -titres », « qu » + « 'ils »)"""
    out = []
    for w in words:
        if out and w["word"][:1] in "-'’" and w["phrase"] == out[-1]["phrase"]:
            out[-1] = dict(out[-1], word=out[-1]["word"] + w["word"], end=w["end"])
        else:
            out.append(dict(w))
    return out


def suggest(edit, lang):
    trig = load(ROOT / "triggers.json")
    D = trig["defaults"]
    lang = lang if lang in ("fr", "en") else "en"
    words = display_words(edit["words"])
    cands = []
    for ph in (p for p in edit["phrases"] if p["kept"]):
        pw = [w for w in words if w["phrase"] == ph["id"]]
        if not pw:
            continue
        pt = [(toks(w["word"]) or [""])[0] for w in pw]  # un token par mot affiché
        flat = []  # (token, index du mot)
        for i, w in enumerate(pw):
            flat += [(t, i) for t in toks(w["word"])]
        ft = [t for t, _ in flat]
        text = " ".join(w["word"] for w in pw)

        def find(kw):
            k = toks(kw)
            for s in range(len(ft) - len(k) + 1):
                ok = all(ft[s + j] == k[j] for j in range(len(k) - 1))
                last = ft[s + len(k) - 1]
                if ok and (last == k[-1] or (len(k[-1]) >= 5 and last.startswith(k[-1]))):
                    return flat[s][1]
            return None

        for r in trig["rules"]:
            hits = []
            for kw in r.get(lang, []):
                i = find(kw)
                if i is not None:
                    hits.append((i, kw))
            for kw, emo in r.get("map", {}).items():
                i = find(kw)
                if i is not None:
                    hits.append((i, emo))
            for rx in r.get("regex", []):
                m = re.search(rx, text, re.I)
                if m:
                    i = next((k for k, w in enumerate(pw) if any(c.isdigit() for c in w["word"])), 0)
                    hits.append((i, m.group(0).strip()))
            if r.get("when") == "question" and text.rstrip().endswith("?"):
                hits.append((0, None))
            if r.get("when") == "proper_noun":
                for i in range(1, len(pw)):
                    if pw[i]["word"][:1].isupper() and not re.search(r"[.?!]$", pw[i - 1]["word"]):
                        j = i
                        while j + 1 < len(pw) and pw[j + 1]["word"][:1].isupper():
                            j += 1
                        name = " ".join(w["word"].strip(".,!?") for w in pw[i:j + 1])
                        if len(name) >= 4:  # pas les sigles courts (PC, OK, IA)
                            hits.append((i, name))
                            break
            for i, val in hits:
                ev = {"at": ph["id"], "word": pw[i]["word"].strip(".,!?"), "fx": r["fx"], "_t": pw[i]["start"],
                      "_prio": r["priority"], "_rule": r["id"]}
                if r["fx"] in ("check", "cross", "card", "cta"):
                    t = r.get("text", "$match")
                    ev["text"] = (val if t == "$match" else t) if val else t
                    ev["text"] = ev["text"][:1].upper() + ev["text"][1:]
                    if r.get("when") == "proper_noun" and val and fetch_logo(val):
                        ev["logo"] = val
                elif r["fx"] == "stat":
                    ev["value"] = val
                elif r["fx"] == "emoji":
                    ev["emoji"] = val
                cands.append(ev)

    cands.sort(key=lambda e: (-e["_prio"], e["_t"]))
    kept, seen = [], set()
    for e in cands:
        key = (e["fx"], e.get("text") or e.get("value") or e.get("emoji") or "")
        if key in seen:
            continue
        group = [k for k in kept if (k["fx"] in OVERLAY_FX) == (e["fx"] in OVERLAY_FX)]
        gap = D["min_gap_s"] if e["fx"] in OVERLAY_FX else 1.5
        if any(abs(k["_t"] - e["_t"]) < gap for k in group):
            continue
        kept.append(e)
        seen.add(key)
    kept.sort(key=lambda e: e["_t"])
    return [{k: v for k, v in e.items() if not k.startswith("_")} for e in kept]


# pistes de démonstration repérées dans le texte (brief « À MONTRER ») : des mots seulement, Claude décide selon le sens
SHOW_SITE = {"couleur": "color", "police": "font", "typo": "font", "flexbox": "flex", "flex": "flex", "grid": "grid", "grides": "grid",
             "grille": "grid", "responsive": "mobile", "mobile": "mobile", "téléphone": "mobile", "menu": "menu", "formulaire": "form",
             "interaction": "click", "clic": "click", "cliquer": "click", "animation": "anim", "animer": "anim", "vivant": "anim"}
SHOW_KIND = [("site", ["html", "css", "page web", "landing page", "interface", "maquette"]),
             ("scene code", ["code", "fonction", "variable", "bug", "clé api", "ligne de code", "script"]),
             ("scene terminal", ["commande", "terminal", "installer", "npm", "git", "pip"]),
             ("scene chat", ["ia", "lia", "chatgpt", "claude", "gpt", "prompt", "assistant"]),
             ("scene compare", ["alors que", "au lieu de", "plutôt que", "avant après"])]
TECH = {"html", "css", "javascript", "typescript", "python", "react", "vue", "angular", "svelte", "node", "figma", "notion", "github",
        "git", "docker", "tailwind", "bootstrap", "wordpress", "shopify", "webflow", "chatgpt", "openai", "claude", "anthropic",
        "canva", "netflix", "youtube", "tiktok", "instagram", "google", "apple", "android", "linux", "windows", "excel", "slack",
        "discord", "stripe", "supabase", "firebase", "vercel", "nextjs", "php", "java", "kotlin", "swift", "rust", "go", "sql", "mysql"}
_ITEM = r"(?:le|la|les|des|du|de|l'|un|une|ton|ta|tes)\s?[\wÀ-ÿ'-]+(?:\s(?:de\s)?[\wÀ-ÿ'-]+){0,2}"
ENUM = re.compile(rf"(?:{_ITEM},\s*){{1,4}}(?:mais\s)?(?:surtout,?\s)?{_ITEM},?\s(?:et|ou)\s(?:surtout\s)?{_ITEM}"
                  rf"|(?:{_ITEM},\s*){{2,4}}{_ITEM}", re.I)


def show_hints(edit):
    """par phrase : énumérations à synchroniser, logos disponibles, démonstrations possibles"""
    out = []
    words = display_words(edit["words"])
    for ph in (p for p in edit["phrases"] if p["kept"]):
        pw = [w["word"] for w in words if w["phrase"] == ph["id"]]
        if not pw:
            continue
        text = " ".join(pw)
        low = " " + " ".join(t for w in pw for t in toks(w)) + " "  # mots entiers, sans accents ni ponctuation
        hints = []
        m = ENUM.search(text)
        if m:
            hints.append(f"énumération « {m.group(0)} » → un élément par mot (steps / list)")
        acts = []
        for w in pw:
            k = (toks(w) or [""])[0]
            a = next((v for kw, v in SHOW_SITE.items() if k.startswith(kw)), None)
            if a and a not in [x[1] for x in acts]:
                acts.append((w.strip(".,!?"), a))
        kinds = [k for k, kws in SHOW_KIND if any(" " + " ".join(toks(kw)) + " " in low for kw in kws)]
        if acts:
            kinds = ["site"] + [k for k in kinds if k != "site"]
        if kinds:
            hints.append(" / ".join(kinds) + (" (" + ", ".join(f"{w}→{a}" for w, a in acts) + ")" if acts else ""))
        logos = []
        for i, w in enumerate(pw):
            name = w.strip(".,!?«»")
            k = (toks(name) or [""])[0]
            if k in TECH or (i and name[:1].isupper() and len(name) >= 4 and not re.search(r"[.?!]$", pw[i - 1])):
                if k not in [toks(x)[0] for x in logos] and fetch_logo(name):
                    logos.append(name)
        if logos:
            hints.append("logo dispo : " + ", ".join(logos))
        if hints:
            out.append(f"{ph['id']}  " + " · ".join(hints))
    return out


# ---------------------------------------------------------------- prepare

def audio16k(wd, video):
    """audio mono 16 kHz de la source (sert au calage des coupes sur l'énergie du son)"""
    p = wd / "audio16k.wav"
    if not p.exists():
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
             "-af", "aresample=async=1:first_pts=0", "-c:a", "pcm_s16le", p], "extraction audio")
    return p


def workdir_for(video):
    """fichiers de travail dans un dossier caché (.montage/<nom>) ; les vidéos finies vont dans output/"""
    old = Path.cwd() / "montage" / Path(video).stem
    return old if old.exists() else Path.cwd() / ".montage" / Path(video).stem


REGEN = ("video_cut.mp4", "overlay.mov", "audio16k.wav", "audio48k.wav", "voice.wav", "round_mask.png", "segments", "overlay")
KEEP_DAYS = 30  # un dossier de travail non touché depuis plus longtemps est supprimé au montage suivant


def clean_workdir(wd):
    """après un rendu final : on ne garde que ce qui ne se recrée pas seul (transcription, plan, planche…, ~1 Mo).
    Audios, calque et coupes se refont depuis le rush en quelques secondes à la retouche suivante."""
    for name in REGEN:
        x = wd / name
        if x.is_dir():
            shutil.rmtree(x, ignore_errors=True)
        else:
            x.unlink(missing_ok=True)


def prune_workdirs(current):
    """ménage au début d'un montage : dossiers dont le rush n'existe plus, ou non touchés depuis KEEP_DAYS jours.
    hooks_history.json (accroches récentes) est toujours gardé."""
    import time
    removed = []
    for root in {current.parent, Path.cwd() / ".montage", Path.cwd() / "montage"}:
        if not root.is_dir():
            continue
        for d in root.iterdir():
            if not d.is_dir() or d.resolve() == current.resolve() or not (d / "meta.json").exists():
                continue
            src = (load(d / "meta.json", {}) or {}).get("video")
            last = max((f.stat().st_mtime for f in d.rglob("*") if f.is_file()), default=d.stat().st_mtime)
            old = time.time() - last > KEEP_DAYS * 86400
            if (src and not Path(src).exists()) or old:
                shutil.rmtree(d, ignore_errors=True)
                removed.append(f"{d.name} ({'rush introuvable' if src and not Path(src).exists() else f'+{KEEP_DAYS} jours'})")
    if removed:
        log("Ménage .montage : " + ", ".join(removed))


def final_path(wd, suffix=""):
    """la vidéo montée, dans le dossier output/ du projet (à côté de .montage/) : output/<nom>_monte.mp4"""
    out = wd.parent.parent / "output"
    out.mkdir(exist_ok=True)
    return out / f"{wd.name}_monte{suffix}.mp4"


def cmd_prepare(a):
    check_env()
    video = Path(a.video).resolve()
    if not video.exists():
        die(f"Vidéo introuvable : {video}")
    wd = workdir_for(video)
    wd.mkdir(parents=True, exist_ok=True)
    prune_workdirs(wd)
    w, h, dur = probe(video)
    meta = {"video": str(video), "width": w, "height": h, "duration": dur, "lang": a.lang}
    save(wd / "meta.json", meta)

    tr_p = wd / "transcript.json"
    if not tr_p.exists() or a.force:
        log(f"1/4 Transcription ({dur:.0f}s de vidéo, modèle {a.model})...")
        cmd = [sys.executable, ROOT / "scripts/transcribe.py", video, "--out", tr_p, "--model", a.model,
               "--keep-audio", wd / "audio16k.wav"]
        if a.lang:
            cmd += ["--lang", a.lang]
        run(cmd, "transcription")
    else:
        log("1/4 Transcription : déjà faite (--force pour refaire)")
    fz_p = wd / "face_zones.json"
    if not fz_p.exists() or a.force:
        log("2/4 Détection du visage...")
        try:
            run([sys.executable, ROOT / "scripts/face_zones.py", video, "--out", fz_p, "--fps", "1"], "visage")
        except SystemExit as e:
            log(f"    [!] visage non détecté, placement par défaut ({e})")
    else:
        log("2/4 Visage : déjà fait")

    log("3/4 Dérushage...")
    tr = load(tr_p)
    plan = load(wd / "plan.json", {})
    edit = derush.build(tr, plan.get("cut", []), plan.get("restore", []), audio16k(wd, video), FPS,
                        plan.get("trim", []), plan.get("tail", derush.TAIL),
                        plan.get("head", 0.0), plan.get("intro"), plan.get("cold_open"))
    save(wd / "edit.json", edit)

    if edit["segments"]:  # planche des 3 s avant le premier mot : repérer un hook visuel à garder (plan.head)
        s0 = edit["segments"][1 if plan.get("intro") and len(edit["segments"]) > 1 else 0]["src_start"] + plan.get("head", 0.0)
        a0 = max(0.0, s0 - 3)
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a0:.2f}", "-t", f"{s0 - a0:.2f}", "-i", video,
             "-vf", "fps=4,scale=150:-1,tile=12x1", "-frames:v", "1", wd / "hook.jpg"], "planche d'ouverture")
        meta["hook_sheet"] = {"start": round(a0, 2), "first_word": round(s0, 2)}
    log("4/4 Suggestions...")
    auto = {"cut": [], "restore": [], "events": suggest(edit, tr.get("language", "fr"))}
    save(wd / "plan.auto.json", auto)
    meta["_wd"] = str(wd)
    brief = make_brief(meta, edit, auto)
    (wd / "brief.txt").write_text(brief, "utf-8")
    log("\n" + brief)
    log(f"Dossier : {wd}")


def make_brief(meta, edit, auto):
    W, H = out_size(meta["width"], meta["height"])
    L = [f"VIDEO {Path(meta['video']).name} {meta['duration']:.0f}s -> {edit['duration']:.1f}s après dérushage ({W}x{H})",
         *([f"OUVERTURE : hook.jpg = les {meta['hook_sheet']['first_word'] - meta['hook_sheet']['start']:.1f} s avant le premier mot "
            f"(image k = k x 0,25 s depuis le début de la planche) : ouvre-la ; geste, objet, main devant l'objectif → "
            f"garde-le avec \"head\" (s avant le premier mot)"] if meta.get("hook_sheet") else []),
         "", "PHRASES GARDÉES (temps final) :"]
    dw = display_words(edit["words"])
    for p in edit["phrases"]:
        if p["kept"] and p["start"] is not None:
            text = " ".join(w["word"] for w in dw if w["phrase"] == p["id"])
            L.append(f"{p['id']} {p['start']:5.1f}-{p['end']:5.1f} {text}" + ("   [murmuré]" if p.get("quiet") else ""))
    kept_ids = [p["id"] for p in edit["phrases"] if p["kept"] and p["start"] is not None]
    L += ["", "TEXTE DU MONTAGE (à relire d'un bloc : chaque info doit n'apparaître qu'une fois) :",
          " ".join(w["word"] for w in dw if w["phrase"] in kept_ids)]
    for err in edit.get("errors", []):
        L.append(f"[!] {err}")
    dropped = [p for p in edit["phrases"] if not p["kept"]]
    if dropped:
        L += ["", "RETIRÉES (restore possible) :"]
        L += [f"~{p['id']} {p['text'][:60]}  [{p['reason']}]" for p in dropped]
    hist = [x for x in (load(Path(meta["_wd"]).parent / "hooks_history.json", []) or []) if x["video"] != Path(meta["_wd"]).name][-6:]
    if hist:
        L += ["", "ACCROCHES RÉCENTES (varie : évite de reprendre la même famille visuelle et le même style de texte) :"]
        L += [f"  {x['video'][:28]:28}  visuel : {', '.join(x['visuel'])}  ·  texte : {x['texte']}" for x in hist]
    L += ["", "À MONTRER (pistes : démontre ce que la phrase décrit, n'écris pas une carte de texte) :"]
    L += show_hints(edit) or ["(rien de repéré : relis quand même chaque phrase)"]
    L += ["", "SUGGESTIONS AUTO (plan.auto.json, mots-clés seulement : à corriger selon le sens) :"]
    for e in auto["events"]:
        extra = " ".join(f'{k}="{v}"' for k, v in e.items() if k not in ("at", "word", "fx"))
        L.append(f"{e['at']} «{e['word']}» {e['fx']} {extra}".rstrip())
    if not auto["events"]:
        L.append("(aucune)")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- render

def locate(e, by_phrase):
    """instant (s, montage) du mot e.word dans la phrase e.at ; renvoie (t, avertissement)"""
    if "t" in e:
        return float(e["t"]), None
    pw = by_phrase.get(e.get("at"))
    if not pw:
        return None, f"{e.get('at')} : phrase absente ou coupée"
    if not e.get("word"):
        return pw[0]["start"], None
    k = toks(e["word"])
    hits = [w for w in pw if k and toks(w["word"])[:len(k)] == k] or \
           [w for w in pw if k and toks(w["word"]) and toks(w["word"])[0].startswith(k[0])]
    n = int(e.get("n", 1))
    if len(hits) >= n:
        return hits[n - 1]["start"], None
    return pw[0]["start"], f"{e['at']} : mot « {e['word']} » introuvable, placé en début de phrase"


TEXT_FX = ("card", "check", "cross", "title", "blob", "emoji", "splash")
SHOW_FX = ("scene", "site", "list", "diagram", "screen", "chart", "number", "percent", "stat", "timer")


def show_check(events):
    """montrer plutôt qu'écrire : signale un montage où le texte l'emporte sur les démonstrations, et les logos oubliés"""
    errs = []
    text = [e for e in events if e["fx"] in TEXT_FX and not e["params"].get("logo")]
    show = [e for e in events if e["fx"] in SHOW_FX or e["params"].get("logo")]
    if len(text) > len(show):
        errs.append(f"plus de texte que de démonstrations ({len(text)} cartes / ✓ / ✗ / titres contre {len(show)}) : "
                    "pour chaque carte, montre plutôt ce dont la phrase parle (site, scene, logo, list ou code à étapes)")
    for e in events:
        if e["fx"] in ("card", "check", "cross", "title") and not e["params"].get("logo"):
            for w in re.findall(r"[\wÀ-ÿ.+#-]{2,}", str(e["params"].get("text", "")).replace("*", "")):
                if (toks(w) or [""])[0] in TECH and fetch_logo(w):
                    errs.append(f"{e['fx']} « {e['params'].get('text')} » : {w} a un logo, ajoute \"logo\": \"{w.lower()}\"")
                    break
    return errs


def resolve_events(plan, edit, words, effects):
    by_phrase = {}
    for w in words:
        by_phrase.setdefault(w["phrase"], []).append(w)
    out, errors = [], []
    for e in plan.get("events", []):
        fx = e.get("fx")
        if fx not in effects:
            errors.append(f"effet inconnu « {fx} »")
            continue
        t, err = locate(e, by_phrase)
        if t is None:
            errors.append(f"{err} ({fx})")
            continue
        if err:
            errors.append(err)
        if fx in ("list", "diagram"):  # chaque point / case apparaît quand il est dit
            items = []
            for it in e.get("items", []):
                ti, err = locate({"at": e.get("at"), **it}, by_phrase)
                if err:
                    errors.append(f"liste : {err}")
                if ti is not None:
                    items.append({"t": round(max(ti, t), 3), "text": it.get("text", ""), "sfx": it.get("sfx", "auto"),
                                  **{k: it[k] for k in ("emoji", "tone", "icon", "logo") if it.get(k)}})
            e = {**e, "items": items}
            if "dur" not in e and items:
                e["dur"] = round(max(x["t"] for x in items) + LIST_HOLD - t, 2)
        if e.get("steps"):  # étapes d'une scène / d'une maquette : chacune se déclenche sur son mot
            steps = []
            for st in e["steps"]:
                ti, err = locate({"at": e.get("at"), **st}, by_phrase)
                if err:
                    errors.append(f"{fx} : {err}")
                if ti is not None:
                    steps.append({**{k: v for k, v in st.items() if k not in ("at", "word", "n")}, "t": round(max(ti, t + 0.45), 3)})
            e = {**e, "steps": sorted(steps, key=lambda x: x["t"])}
            if "dur" not in e and steps:
                e["dur"] = round(max(x["t"] for x in steps) + STEP_HOLD - t, 2)
        if fx == "timer" and "dur" not in e:  # reste à l'écran jusqu'à 0:00 (+ 1,5 s), ou la fin de la vidéo
            e = {**e, "dur": float(e.get("from", 60)) + 1.5}
        params = {k: v for k, v in e.items() if k not in ("at", "word", "n", "fx", "dur", "sfx", "t")}
        out.append({"fx": fx, "t": round(t, 3), "dur": float(e.get("dur", effects[fx]["dur"])),
                    "params": params, "sfx": e.get("sfx", "auto")})
    total = edit["duration"]
    for x in out:  # un effet ne doit pas déborder de la fin de la vidéo
        if x["dur"] and x["t"] + x["dur"] > total - 0.05:
            if x["fx"] in ("list", "diagram", "timer") or x["params"].get("steps"):  # calé sur la parole : on raccourcit sans déplacer
                x["dur"] = max(total - 0.05 - x["t"], 0.5)
                continue
            x["t"] = round(max(min(x["t"], total - 1.5), 0), 3)
            x["dur"] = max(total - 0.05 - x["t"], 0.3)
    out.sort(key=lambda x: x["t"])
    # zone haute : un seul élément à la fois, le précédent s'efface avant le suivant
    top = [x for x in out if effects[x["fx"]]["zone"] == "top"]
    for a, b in zip(top, top[1:]):
        if a["t"] + a["dur"] > b["t"] - 0.05:
            a["dur"] = max(b["t"] - 0.05 - a["t"], 0.5)
    for x in out:  # une liste / un schéma raccourci ne garde que les points dits pendant qu'il est affiché
        if x["fx"] in ("list", "diagram"):
            x["params"]["items"] = [i for i in x["params"]["items"] if i["t"] < x["t"] + x["dur"] - 0.6]  # lisible au moins 0,6 s
        if x["params"].get("steps"):  # une étape qui tomberait après la fin n'est pas jouée
            x["params"]["steps"] = [i for i in x["params"]["steps"] if i["t"] < x["t"] + x["dur"] - 0.5]
    return out, errors


def apply_fixes(words, fixes):
    """corrige le texte des sous-titres (erreurs de transcription) sans toucher au son :
    plan.fix = [{at, from, to}] ; les mots de `to` se partagent le temps des mots de `from`"""
    out, errors = list(words), []
    for f in fixes:
        src = [derush.norm_word(x) for x in f["from"].split()]
        idx = [k for k, w in enumerate(out) if w["phrase"] == f["at"]]
        hit = next((k for k in idx if [derush.norm_word(out[j]["word"]) for j in range(k, min(k + len(src), len(out)))] == src), None)
        if hit is None:
            errors.append(f"fix {f['at']} : « {f['from']} » introuvable")
            continue
        old = out[hit:hit + len(src)]
        new = f["to"].split()
        a, b = old[0]["start"], old[-1]["end"]
        step = (b - a) / max(1, len(new))
        out[hit:hit + len(src)] = [{**old[0], "word": w, "start": round(a + i * step, 3), "end": round(a + (i + 1) * step, 3)}
                                   for i, w in enumerate(new)]
    return out, errors


def caption_groups(words, events):
    hl = {round(e["t"], 3) for e in events if e["fx"] == "highlight"}
    dw = display_words(words)
    groups, cur = [], []
    for i, w in enumerate(dw):
        txt = w["word"].strip(",.;:…")
        if not txt:
            continue
        cur.append({"w": txt, "s": w["start"], "e": w["end"], "hl": round(w["start"], 3) in hl})
        nxt = dw[i + 1] if i + 1 < len(dw) else None
        chars = sum(len(x["w"]) for x in cur)
        if (not nxt or len(cur) >= 3 or chars >= 14 or re.search(r"[,.;:?!…]$", w["word"])
                or nxt["start"] - w["end"] > 0.35 or nxt["phrase"] != w["phrase"]):
            groups.append(cur)
            cur = []
    out = []
    for i, g in enumerate(groups):
        start = g[0]["s"]
        nstart = groups[i + 1][0]["s"] if i + 1 < len(groups) else None
        end = nstart if nstart is not None and nstart - g[-1]["e"] < 0.6 else g[-1]["e"] + 0.25
        for j, w in enumerate(g):
            w["next"] = g[j + 1]["s"] if j + 1 < len(g) else end
        out.append({"start": round(start, 3), "end": round(end, 3), "words": g})
    return out


def zones(meta, W, H, flip=False, platform="all"):
    fz = load(Path(meta["_wd"]) / "face_zones.json")
    if not fz:
        sf = PLATFORMS.get(platform, PLATFORMS["all"])
        return {"top": {"y": int(H * (sf["top"] + 0.01)), "h": int(H * .2)}, "face": None,
                "cap": {"x": int(W * .06), "y": int(H * sf["bottom"]) - int(H * .14), "w": int(W * (sf["right"] - .08)),
                        "h": int(H * .14)}}, 0.4
    sx, sy = W / fz["width"], H / fz["height"]
    cb = fz["caption_box"]
    cap = {"x": int(cb["x"] * sx), "y": int(cb["y"] * sy), "w": int(cb["w"] * sx), "h": int(cb["h"] * sy)}
    if flip:  # image retournée (plan.mirror = true) : la zone des sous-titres aussi
        cap["x"] = W - cap["x"] - cap["w"]
    f = fz.get("face")
    top_y = int(H * 0.08)
    if f:
        bottom = int((f["y"] + 0.2 * f["h"]) * sy)
        fy = (f["y"] + 0.45 * f["h"]) / fz["height"]
    else:
        bottom, fy = int(H * 0.3), 0.4
    top_h = max(bottom - top_y, int(H * 0.14))
    face = None
    if f:  # visage en coordonnées de sortie (coins de cadre)
        face = {"x": int(f["x"] * sx), "y": int(f["y"] * sy), "w": int(f["w"] * sx), "h": int(f["h"] * sy)}
        if flip:
            face["x"] = W - face["x"] - face["w"]
    sf = PLATFORMS.get(platform, PLATFORMS["all"])
    top_y = max(top_y, int(H * (sf["top"] + 0.01)))  # sous la barre du haut de l'appli
    cap["y"] = min(cap["y"], int(H * sf["bottom"]) - cap["h"])  # sous-titres au-dessus du nom / de la description
    cap["w"] = min(cap["w"], int(W * sf["right"]) - cap["x"])  # à gauche du rail de boutons
    return {"top": {"y": top_y, "h": top_h}, "cap": cap, "face": face}, fy


def perceived_db(path, af=""):
    """niveau perçu d'un son, même court (un pop dure 50 ms, trop court pour la mesure EBU R128) :
    RMS max sur 100 ms après une pondération K approchée (les aigus d'un ding paraissent plus forts)"""
    import numpy as np
    f = "highpass=f=60,treble=g=4:f=1500" + ("," + af if af else "")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-af", f, "-ac", "1", "-ar", "48000",
                          "-f", "f32le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.float32).astype(np.float64)
    w = 4800
    if len(x) < w:
        x = np.pad(x, (0, w - len(x)))
    e = np.convolve(x ** 2, np.ones(w) / w, "valid")
    return 10 * np.log10(e.max() + 1e-12)


def sfx_gains(sfx, voice, D, offset_db):
    """gain de chaque son pour qu'il sonne à niveau constant sous la voix normalisée,
    quel que soit le niveau du fichier ; ±3 dB selon l'intensité (1 discret, 3 marquant)"""
    ref = perceived_db(voice, VOICE_NORM) + D["sfx_rel_db"] + offset_db
    cache = {}
    for s in sfx:
        if s["file"] not in cache:
            cache[s["file"]] = (perceived_db(s["file"]), sfx_onset(s["file"]))
        s["gain"] = round(ref + 3 * (s["intensity"] - 2) - cache[s["file"]][0], 1)
        s["onset"] = sfx_peak(s["file"]) if s.get("align") == "peak" else cache[s["file"]][1]


def number_value(raw):
    """valeur numérique de "10 000 €", "87 %", "x3" (None si pas de chiffre)"""
    m = re.search(r"\d(?:[\d\s.,]*\d)?", str(raw))
    return float(re.sub(r"\s", "", m.group()).replace(",", ".")) if m else None


def add_counts(events):
    """minutage des chiffres qui défilent, défini ici une seule fois : le calque (e.count) et les tics
    du compteur (counter_sfx) l'utilisent tous les deux, ils restent donc synchrones"""
    for e in events:
        p, dur, c = e["params"], e["dur"], []
        if e["t"] < 0.05 and e["fx"] in ("number", "percent", "stat"):  # ouverture : valeur finale affichée, pas de compteur
            e["count"], e["_count"], e["typing"] = [], [], []
            continue
        if e["fx"] == "stat":
            c = [(e["t"], min(0.9, dur * 0.45), number_value(p.get("value")))]
        elif e["fx"] in ("number", "percent"):
            c = [(e["t"] + 0.1, min(1.1, dur * 0.45), number_value(p.get("value")))]
        elif e["fx"] == "chart":
            data = [d for d in p.get("data", []) if number_value(d.get("value")) is not None]
            t0 = e["t"] + 0.3
            if p.get("kind", "bar") == "bar":
                grow, gap = min(0.7, dur * 0.3), min(0.18, dur * 0.4 / max(1, len(data)))
                c = [(t0 + i * gap, grow, number_value(d["value"])) for i, d in enumerate(data)]
            elif data:
                hi = p.get("highlight", len(data) - 1)
                c = [(t0 + min(1.2, dur * 0.4), 0.5, number_value(data[hi]["value"]))]
        e["count"] = [{"t": round(t, 3), "d": round(d, 3)} for t, d, v in c]
        # frappe des scènes code / terminal : même source pour l'animation (e.typing) et le son de clavier
        e["typing"] = []
        if e["fx"] == "scene" and p.get("kind", "code") in ("code", "terminal"):
            T0, span = e["t"] + 0.4, max(0.6, dur - 1.2)
            if p.get("kind", "code") == "code":
                n = max(1, len(p.get("lines", [])))
                per = span * 0.6 / n
                if p.get("steps"):  # lignes surlignées au fil de la parole : le code est déjà tapé à la 1re étape
                    per = min(1.4, max(0.5, p["steps"][0]["t"] - T0 - 0.15)) / n
                e["typing"] = [{"t": round(T0 + i * per, 3), "d": round(per * 0.9, 3)} for i in range(n)]
            else:
                t, lines = T0, p.get("lines", [])
                for l in lines:
                    if isinstance(l, dict) and l.get("cmd"):
                        d = min(0.9, span * 0.3)
                        e["typing"].append({"t": round(t, 3), "d": round(d, 3)})
                        t += d + 0.15
                    else:
                        t += span * 0.6 / max(1, len(lines))
        e["_count"] = [(t, d, v) for t, d, v in c if v]


def counter_sfx(wd, events, D):
    """tics de compteur synthétisés (aucun fichier son, aucune licence) : un tic par palier du chiffre,
    serrés au début puis espacés, comme le défilement (ease power2.out), plafonnés à ~28 tics/s"""
    import numpy as np
    import wave
    sr, out = 48000, []
    for k, e in enumerate(events):
        if not e.get("_count") or e["sfx"] in (None, "none", False):
            continue
        ticks = []
        for t, d, v in e["_count"]:
            n = int(max(6, min(abs(v), d * 28)))
            ticks += [t + (1 - (1 - j / n) ** 0.5) * d for j in range(1, n + 1)]
        kept = []
        for x in sorted(ticks):  # au moins 22 ms entre deux tics (sinon ils se fondent en un bourdonnement)
            if not kept or x - kept[-1] > 0.022:
                kept.append(x)
        ticks = kept
        start = ticks[0]
        y = np.zeros(int((ticks[-1] - start + 0.1) * sr))
        tt = np.arange(int(0.012 * sr)) / sr
        rng = np.random.default_rng(k)
        for i, x in enumerate(ticks):  # clic : sinus aigu qui monte légèrement + souffle bref, décroissance rapide
            f = 2600 * (1 + 0.35 * i / len(ticks))
            click = (np.sin(2 * np.pi * f * tt) + 0.4 * rng.standard_normal(len(tt))) * np.exp(-tt / 0.0025)
            a = int((x - start) * sr)
            y[a:a + len(click)] += click[:len(y) - a]
        y = (y / (np.abs(y).max() or 1) * 0.8 * 32767).astype(np.int16)
        f = wd / "sfx_gen" / f"counter_{k}.wav"
        f.parent.mkdir(exist_ok=True)
        with wave.open(str(f), "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(y.tobytes())
        out.append({"file": f, "t": start, "intensity": 1})
    return out


# durée max (s) de chaque son = durée de l'animation qu'il accompagne ; au-delà, fondu et coupe
SFX_LEN = {"glitch": 0.45, "shake": 0.7, "punch": 0.6, "hook": 0.8, "flash": 0.5, "zoom": 0.6, "strike": 0.9,
           "burst": 0.8, "impact": 0.9, "item": 0.6, "enter": 0.8}


def sfx_len(e):
    fx, p = e["fx"], e["params"]
    if fx == "hook_sfx":
        return SFX_LEN.get(p.get("kind"), SFX_LEN["hook"])
    if fx in ("flash", "zoom"):
        return SFX_LEN[fx]
    if fx in ("number", "percent", "blob"):
        return SFX_LEN["impact"]
    if fx == "splash":
        return max(0.6, e["dur"])
    return min(SFX_LEN["enter"], max(0.3, e["dur"] or 0.8))


def cue_time(e):
    """instant fort de l'animation, où le son doit tomber (même minutage que engine/effects.js)"""
    c = e.get("count") or []
    if e["fx"] in ("number", "percent", "stat") and c and e["params"].get("burst") or e["fx"] in ("number", "percent") and c:
        return c[0]["t"] + c[0]["d"]  # fin du compteur : rebond / éclaboussure
    if e["fx"] == "blob":
        return e["t"] + 0.15  # éclaboussure
    if e["fx"] == "emoji" and e["params"].get("burst"):
        return e["t"] + 0.1
    return e["t"]


def sfx_peak(path):
    """instant du pic d'un son qui monte vers un impact (cymbale inversée, riser) : c'est lui qu'on cale sur l'image"""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.abs(np.frombuffer(raw, np.float32))
    return float(np.convolve(x, np.ones(480) / 480, "same").argmax()) / 48000 if len(x) else 0.0


def sfx_onset(path):
    """début audible du fichier (s) : beaucoup de sons commencent par un court silence ; c'est l'attaque, pas le
    début du fichier, qu'on cale sur l'image"""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "48000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.abs(np.frombuffer(raw, np.float32))
    if not len(x):
        return 0.0
    hit = np.nonzero(x > 0.15 * x.max())[0]
    return float(hit[0]) / 48000 if len(hit) else 0.0


def pick_sfx(events, effects, D):
    """un son par effet (et par point de liste), tiré d'un pool de familles « catégorie/tag » ;
    jamais deux fois le même fichier dans les 3 derniers, pour éviter l'effet « ding, ding, ding »"""
    manifest = load(ROOT / "library/manifest.json", {"assets": []})["assets"]
    rng = random.Random(1)
    hits = []  # (t, choix explicite ou None, spec, durée max) : chaque son est coupé à la durée de son animation
    for e in events:
        fxd = effects.get(e["fx"], {})
        spec = fxd.get("sfx_kinds", {}).get(e["params"].get("kind")) or fxd.get("sfx")
        impact = cue_time(e)
        if e["params"].get("burst") and e["fx"] != "blob":  # éclaboussure : un impact pile quand elle jaillit
            hits.append((impact, "auto" if e["sfx"] == "auto" else e["sfx"], {"pool": ["impacts/hit"], "max_intensity": 2},
                         SFX_LEN["burst"]))
            if e["fx"] in ("stat",):  # le chiffre apparaît (pop) puis jaillit en fin de compteur (impact)
                hits.append((e["t"], e["sfx"], spec, sfx_len(e)))
            continue
        if e.get("typing"):  # clavier : un son par bloc de frappe continu, coupé à la durée de la frappe
            blocks = []
            for x in e["typing"]:
                if blocks and x["t"] - (blocks[-1][0] + blocks[-1][1]) < 0.2:
                    blocks[-1][1] = x["t"] + x["d"] - blocks[-1][0]
                else:
                    blocks.append([x["t"], x["d"]])
            hits += [(a, e["sfx"], spec, d) for a, d in blocks]
        else:
            hits.append((impact, e["sfx"], spec, sfx_len(e)))
        if e["fx"] == "screen" and e["params"].get("strike"):  # le trait rouge qui barre la page
            hits.append((e["t"] + STRIKE_AT + STRIKE_DRAW, "auto", {"pool": ["impacts/hit"], "max_intensity": 2}, SFX_LEN["strike"]))
        for it in e["params"].get("items", []) if e["fx"] in ("list", "diagram") else []:
            hits.append((it["t"], it["sfx"], effects[e["fx"]].get("item_sfx"), SFX_LEN["item"]))
        for st in e["params"].get("steps", []):  # maquette / scène : un son par étape, selon l'action
            ss = fxd.get("step_sfx", {})
            hits.append((st["t"], st.get("sfx", "auto"), ss.get(st.get("do")) or ss.get("default"), SFX_LEN["item"]))
            if st.get("do") == "form":  # frappe dans les champs du formulaire
                hits.append((st["t"] + 0.5, "ui/keyboard", None, 1.1))
    hits = [h if len(h) == 4 else (*h, None) for h in hits]  # 4e champ : durée max du son (None = entier)
    UNCUT = ("impacts/",)  # un boom / impact garde toute sa résonance : le couper sonne faux
    hits.sort(key=lambda h: h[0])
    used, loud, out = [], -99.0, []
    for t, s, spec, cut in hits:
        if s in (None, "none", False):
            continue  # (un élément posé à 0 s est un hook visuel : son son tombe sur la 1re image)
        align = None
        if s == "reveal":  # révélation (solution, leçon) : la montée de cymbale culmine pile sur l'instant
            s, align, cut = "transitions/reverse_symbal", "peak", None
        if s != "auto":
            rel = "sfx/" + (s if s.endswith(".wav") else s + ".wav")
            x = next((x for x in manifest if x["file"] == rel), {})
            if (ROOT / "library" / rel).exists():
                out.append({"file": ROOT / "library" / rel, "t": t, "intensity": x.get("intensity") or 2,
                            "dur": None if rel.startswith(tuple("sfx/" + u for u in UNCUT)) else cut, "align": align})
                used.append(rel)
            continue
        if not spec:
            continue
        maxi = spec.get("max_intensity", 3)
        if t - loud < D["intensity3_gap_s"]:
            maxi = min(maxi, 2)
        fams = spec.get("pool") or [f"{spec['category']}/{spec['tag']}"]
        pool = [x for x in manifest if x["type"] == "sfx" and (x.get("intensity") or 1) <= maxi
                and any(x["category"] == f.split("/")[0] and f.split("/")[1] in x.get("tags", []) for f in fams)]
        pool = [x for x in pool if x["file"] not in used[-3:]] or [x for x in pool if used[-1:] != [x["file"]]] or pool
        if not pool:
            continue
        x = rng.choice(pool)
        used.append(x["file"])
        if (x.get("intensity") or 1) >= 3:
            loud = t
        out.append({"file": ROOT / "library" / x["file"], "t": t, "intensity": x.get("intensity") or 1,
                    "dur": None if x["file"].startswith(tuple("sfx/" + u for u in UNCUT)) else cut})
    return out


ZOOM_RULES = {"first_toggle_s": 1.5,   # rien ne bouge pendant l'accroche
              "toggle_gap_s": 2.5,     # au moins 2,5 s entre deux changements de cadre aux coupes
              "punch_gap_s": 4.0,      # au moins 4 s entre deux zooms punch
              "quiet_before_punch_s": 1.0, "quiet_after_punch_s": 0.5}


def zoom_expr(edit, events, cut_zoom, hook_punch=None):
    """z(it) : niveau fixe par plan (alterné aux coupes pour masquer les jump cuts) + zooms punch.
    Règles (ZOOM_RULES) pour éviter le « zoom, re-zoom, dézoom » : on n'alterne qu'aux coupes entre deux
    phrases (pas sur un blanc retiré au milieu d'une phrase), jamais pendant l'accroche ni autour d'un
    punch ; un punch vise une taille absolue (il ne s'ajoute pas au zoom de coupe) et reste espacé."""
    R = ZOOM_RULES
    punches, last = [], -99.0
    for e in sorted((e for e in events if e["fx"] == "zoom"), key=lambda e: e["t"]):
        if e["t"] - last >= R["punch_gap_s"]:
            punches.append(e)
            last = e["t"]
    starts = {p["start"] for p in edit["phrases"] if p["kept"] and p["start"] is not None}

    def near_punch(t):
        return any(p["t"] - R["quiet_before_punch_s"] <= t <= p["t"] + p["dur"] + R["quiet_after_punch_s"] for p in punches)

    terms, level, last_toggle, levels = [], 1.0, -99.0, []
    segs = edit["segments"]
    for i, s in enumerate(segs):
        t = s["out_start"]
        between_phrases = any(abs(t - st) < 0.15 for st in starts)
        if (i and cut_zoom and between_phrases and t >= R["first_toggle_s"]
                and t - last_toggle >= R["toggle_gap_s"] and not near_punch(t)):
            level = cut_zoom if level == 1.0 else 1.0
            last_toggle = t
        end = segs[i + 1]["out_start"] if i + 1 < len(segs) else 1e6
        levels.append((t, end, level))
        if level != 1.0:
            terms.append(f"{level - 1:.3f}*between(it,{t:.3f},{end - 0.001:.3f})")
    for e in punches:
        lvl = next((l for a, b, l in levels if a <= e["t"] < b), 1.0)
        k = float(e["params"].get("scale", 1.15)) - lvl  # taille absolue visée, pas un ajout au zoom de coupe
        if k <= 0.02:
            continue
        t0, t1 = e["t"], e["t"] + e["dur"]
        terms.append(f"{k:.3f}*clip((it-{t0:.3f})/0.12,0,1)*clip(({t1:.3f}-it)/0.25,0,1)")
    if hook_punch:  # zoom brutal d'ouverture : l'image part très serrée et se desserre en 0,35 s
        terms.append(f"{float(hook_punch) - 1:.3f}*(1-clip(it/0.35,0,1))")
    return "1+" + "+".join(terms) if terms else "1"


def panel_need(e):
    """hauteur (fraction de l'écran) dont le panneau du haut a besoin pour ce contenu, à taille de texte lisible"""
    p, fx = e["params"], e["fx"]
    if fx == "list":
        # taille du texte limitée par la largeur du point le plus long (comme dans effects.js) : la hauteur en découle
        n = max([len(str(i.get("text", "")).replace("*", "")) for i in p.get("items", [])] + [8])
        f = min(110 / 1920, (0.86 * 9 / 16) / (n * 0.6 + 2.2))  # taille de police en fraction de la hauteur (écran 9:16)
        return 0.03 + (f * 1.6 if p.get("title") else 0) + f * 1.75 * max(1, len(p.get("items", [])))
    if fx == "scene":
        kind = p.get("kind", "code")
        if kind == "code":
            return 0.08 + 0.035 * len(p.get("lines", [])) + (0.05 if (p.get("highlight") or {}).get("note") else 0)
        if kind == "terminal":
            return 0.08 + 0.035 * len(p.get("lines", []))
        if kind == "chat":  # chaque message prend autant de lignes que sa longueur l'impose (~26 caractères par ligne)
            lines = sum(1 + len(str(m.get("text", ""))) // 26 for m in p.get("messages", []))
            return 0.08 + 0.045 * lines + 0.025 * len(p.get("messages", []))
        return 0.24
    if fx == "site":  # maquette de site : assez haute pour que la page se lise
        return 0.3
    if fx == "diagram":
        kind, n = p.get("kind", "flow"), len(p.get("items", []))
        base = {"flow": 0.2 if n <= 4 else 0.32, "hub": 0.32, "cycle": 0.32, "tree": 0.3}.get(kind, 0.3)
        return base + (0.05 if p.get("title") else 0)
    return 0.34  # capture de site, graphique : le plus de place possible


def list_windows(events, safe_top=0.12):
    """fenêtres où la vidéo rétrécit en bas (listes, graphiques, captures et scènes en split) : (début, fin, taille).
    La taille s'adapte au contenu du panneau : peu de contenu, vidéo plus grande ; beaucoup, vidéo plus petite."""
    win = []
    for e in events:
        if e["fx"] in ("list", "chart", "diagram", "site") or (e["fx"] in ("screen", "scene") and e["params"].get("mode", "split") == "split"):
            sc = 1 - LIST_MARGIN - (safe_top + 0.01) - panel_need(e) - 0.02
            win.append((e["t"], e["t"] + e["dur"], round(min(LIST_SCALE_MAX, max(LIST_SCALE_MIN, sc)), 3)))
    out = []
    for a, b, sc in sorted(win):  # deux fenêtres presque collées : la vidéo reste petite entre les deux
        if out and a - out[-1][1] < 0.8:
            out[-1] = (out[-1][0], max(out[-1][1], b), min(out[-1][2], sc))
        else:
            out.append((a, b, sc))
    return out

LOGOS = ROOT / "library" / "logos"  # cache des logos téléchargés (Simple Icons, CC0 ; les marques restent à leurs titulaires)


def logo_slug(name):
    """« React » -> react, « Next.js » -> nextdotjs, « HTML » -> html5 (nommage Simple Icons)"""
    n = str(name).strip().lower().replace("+", "plus").replace(".", "dot").replace("&", "and")
    n = re.sub(r"[^a-z0-9]", "", n)
    return {"html": "html5", "js": "javascript", "css3": "css", "ts": "typescript", "node": "nodedotjs",
            "nodejs": "nodedotjs", "vue": "vuedotjs", "next": "nextdotjs", "nextjs": "nextdotjs"}.get(n, n)


def fetch_logo(name):
    """logo officiel en couleur (SVG) depuis Simple Icons, en cache dans library/logos ; None s'il n'existe pas"""
    slug = logo_slug(name)
    dst = LOGOS / f"{slug}.svg"
    if dst.exists():
        return dst
    miss_p = LOGOS / "_missing.json"
    missing = set(load(miss_p, []) or [])
    if not slug or slug in missing:
        return None
    import urllib.request
    for url in (f"https://cdn.simpleicons.org/{slug}", f"https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg"):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "montage-skill"}), timeout=15) as r:
                svg = r.read()
            if b"<svg" in svg:
                LOGOS.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(svg)
                return dst
        except Exception:
            continue
    LOGOS.mkdir(parents=True, exist_ok=True)
    save(miss_p, sorted(missing | {slug}))
    return None


def attach_logos(events, ov):
    """params.logo (et items[].logo) : télécharge le logo et le copie dans le calque (logos/<slug>.svg)"""
    errors = []
    for e in events:
        for x in [e["params"]] + [i for i in e["params"].get("items", []) if isinstance(i, dict)]:
            if not x.get("logo"):
                continue
            src = fetch_logo(x["logo"])
            if not src:
                errors.append(f"logo « {x['logo']} » introuvable sur Simple Icons (essaie le nom exact du produit) : retiré")
                x.pop("logo")
                continue
            (ov / "logos").mkdir(exist_ok=True)
            shutil.copy(src, ov / "logos" / src.name)
            x["logo"] = f"logos/{src.name}"
    return errors


def capture(wd, params):
    """capture (en cache) de la page params.url, en vue mobile par défaut (lisible sur téléphone,
    même dans le cadre du mode split) ; "mobile": false pour la version bureau"""
    import hashlib
    mobile = params.get("mobile", True)
    focus = params.get("focus", "")
    version = hashlib.sha1((ENGINE / "capture.mjs").read_bytes()).hexdigest()[:6]  # script modifié = nouvelle capture
    key = hashlib.sha1(f"{params['url']}|{mobile}|{focus}|{version}".encode()).hexdigest()[:12]
    img = wd / "screens" / f"{key}.jpg"
    if not img.exists() or not Path(str(img) + ".json").exists():
        img.parent.mkdir(exist_ok=True)
        cmd = ["node", ENGINE / "capture.mjs", params["url"], img] + (["--mobile"] if mobile else []) \
            + (["--focus", focus] if focus else [])
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
        if r.returncode:
            return None, (r.stderr.strip().splitlines() or ["échec"])[-1]
    return img, load(Path(str(img) + ".json"))


def attach_captures(wd, events, ov=None):
    """capture les sites des effets screen ; renvoie les erreurs (l'effet est alors retiré)"""
    errors = []
    for e in [e for e in events if e["fx"] == "screen"]:
        img, info = capture(wd, e["params"])
        if not img:
            errors.append(f"screen {e['params']['url']} : {info}")
            events.remove(e)
            continue
        e["params"].update(img=f"screens/{img.name}", img_w=info["width"], img_h=info["height"],
                           title=info.get("title", ""), shot=str(img),
                           domain=re.sub(r"^https?://(www\.)?", "", info["url"]).split("/")[0])
        if ov:
            (ov / "screens").mkdir(exist_ok=True)
            shutil.copy(img, ov / "screens" / img.name)
    return errors


def hook_kinds(plan):
    """familles d'accroche utilisées par un plan (historique pour varier d'une vidéo à l'autre)"""
    k = []
    if plan.get("head") or plan.get("intro"): k.append("geste filmé")
    for e in plan.get("events", []):
        if e.get("t", 9) < 0.1 and e.get("fx") != "hook":
            k.append({"screen": "capture barrée" if e.get("strike") else "capture", "number": "chiffre choc",
                      "percent": "chiffre choc", "scene": "scène", "blob": "mot choc", "title": "mot choc"}.get(e["fx"], e["fx"]))
    if plan.get("cold_open"): k.append("flash-forward")
    if plan.get("hook_punch"): k.append("zoom brutal")
    if plan.get("hook_shake"): k.append("secousse")
    if plan.get("hook_glitch"): k.append("glitch")
    h = next((e for e in plan.get("events", []) if e.get("fx") == "hook"), None)
    return {"visuel": k or ["aucun"], "texte": (h or {}).get("style", "block") if h else "aucun"}


def record_hooks(wd, plan):
    hist_p = wd.parent / "hooks_history.json"
    hist = [x for x in (load(hist_p, []) or []) if x.get("video") != wd.name]
    hist.append({"video": wd.name, **hook_kinds(plan)})
    save(hist_p, hist[-30:])


def cmd_sheet(a):
    """planche de contrôle du rendu : une image par effet (+ début et fin), zone libre du réseau tracée en rouge.
    C'est l'IA qui la regarde et juge (débordement, texte sous l'interface, chevauchement) : rien n'est corrigé ici."""
    wd = Path(a.workdir).resolve()
    out = final_path(wd)
    if not out.exists():
        die("lance d'abord render")
    data = load(wd / "overlay_plan.json") or die("lance d'abord render (version principale)")
    dur = float(probe(out)[2])
    shots = [(0.05, "début (miniature)")] + [(e["t"] + min(e["dur"] * 0.55, 1.0), e["fx"]) for e in data["events"]
                                          if e["fx"] not in ("highlight",)][:22] + [(dur - 0.3, "fin")]
    sf = data["safe"]
    box = (f"drawbox=x=0:y=ih*{sf['top']}:w=iw:h=3:color=red,drawbox=x=0:y=ih*{sf['bottom']}:w=iw:h=3:color=red,"
           f"drawbox=x=iw*{sf['right']}:y=0:w=3:h=ih:color=red")
    tiles = wd / "sheet_tiles"
    shutil.rmtree(tiles, ignore_errors=True)
    tiles.mkdir()
    for k, (t, _) in enumerate(shots):
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(0, t):.2f}", "-i", out, "-frames:v", "1",
             "-vf", f"{box},scale=200:-2", tiles / f"{k:02d}.png"], "image de contrôle")
    cols = 8
    run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "1", "-i", tiles / "%02d.png",
         "-vf", f"tile={cols}x{-(-len(shots) // cols)}:padding=6:color=white", "-frames:v", "1", wd / "sheet.jpg"], "planche")
    shutil.rmtree(tiles, ignore_errors=True)
    log(f"{wd / 'sheet.jpg'}  (lignes rouges = zone libre « {data.get('platform', '')} » : rien d'important au-dessus, en dessous ni à droite)")
    for k, (t, fx) in enumerate(shots):
        log(f"  {k + 1:2d}. {t:5.1f}s  {fx}")


def cmd_shots(a):
    """capture les sites des effets screen de plan.json et affiche les images à vérifier"""
    wd = Path(a.workdir).resolve()
    plan = load(wd / "plan.json") or die("plan.json absent")
    for e in plan.get("events", []):
        if e.get("fx") != "screen":
            continue
        img, info = capture(wd, e)
        log(f"{e.get('at')} {e['url']} -> " + (f"{img}  ({info.get('title', '')})" if img else f"[!] {info}"))


# zones libres de l'interface de chaque réseau (fractions de l'écran) et position de ses boutons, relevées sur
# captures iPhone : texte et sous-titres restent entre top et bottom, à gauche de right ; « all » = zone commune, pas de flèche
PLATFORMS = {
    "tiktok": {"top": 0.10, "bottom": 0.74, "right": 0.86, "targets": {
        "follow": [0.92, 0.415], "like": [0.92, 0.505], "comment": [0.92, 0.58], "save": [0.92, 0.66], "share": [0.92, 0.735],
        "description": [0.3, 0.80]}},
    "reels": {"top": 0.11, "bottom": 0.77, "right": 0.87, "targets": {
        "follow": [0.56, 0.80], "like": [0.92, 0.445], "comment": [0.92, 0.53], "share": [0.92, 0.70], "description": [0.4, 0.85]}},
    "shorts": {"top": 0.10, "bottom": 0.67, "right": 0.84, "targets": {
        "follow": [0.3, 0.69], "like": [0.92, 0.50], "comment": [0.92, 0.57], "save": [0.92, 0.64], "share": [0.92, 0.71],
        "description": [0.4, 0.73]}},
}
PLATFORMS["all"] = {"top": max(v["top"] for v in PLATFORMS.values()), "bottom": min(v["bottom"] for v in PLATFORMS.values()),
                    "right": min(v["right"] for v in PLATFORMS.values()), "targets": None}
LIST_MARGIN = 0.03  # marge sous la vidéo rétrécie (fraction de la hauteur)
LIST_RADIUS = 0.06  # rayon des coins de la vidéo rétrécie (fraction de la largeur, avant réduction)


def round_mask(wd, W, H):
    """masque à coins arrondis (blanc dedans) : appliqué à la vidéo quand elle rétrécit"""
    m = wd / "round_mask.png"
    if not m.exists():
        R = int(W * LIST_RADIUS)
        corner = "+".join(f"(({xc})*({yc})*gt(hypot({dx},{dy}),{R}))" for xc, yc, dx, dy in [
            (f"lt(X,{R})", f"lt(Y,{R})", f"{R}-X", f"{R}-Y"), (f"gt(X,W-{R})", f"lt(Y,{R})", f"X-(W-{R})", f"{R}-Y"),
            (f"lt(X,{R})", f"gt(Y,H-{R})", f"{R}-X", f"Y-(H-{R})"), (f"gt(X,W-{R})", f"gt(Y,H-{R})", f"X-(W-{R})", f"Y-(H-{R})")])
        run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c=white:s={W}x{H}:d=1",
             "-vf", f"format=gray,geq=lum='255*not({corner})'", "-frames:v", "1", m], "masque arrondi")
    return m


def layout_filter(events, W, H, mask_in, safe_top=0.12):
    """pendant une liste / un graphique / une capture split, la vidéo rétrécit en bas (coins arrondis,
    marge, fond flouté) pour libérer le haut ; l'ombre portée est dessinée par le calque d'animations"""
    win = list_windows(events, safe_top)
    if not win:
        return ["[vz]null[vl]"]
    ramps = [f"clip((t-{a:.3f})/0.35,0,1)*clip(({b:.3f}-t)/0.35,0,1)" for a, b, _ in win]
    sc = "(1-(" + "+".join(f"{1 - s:.3f}*{r}" for (_, _, s), r in zip(win, ramps)) + "))"
    size = f"w='trunc({W}*{sc}/2)*2':h='trunc({H}*{sc}/2)*2':eval=frame"
    lift = f"{LIST_MARGIN * H:.1f}*(" + "+".join(ramps) + ")"  # la marge apparaît avec la réduction
    on = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b, _ in win)
    return ["[vz]split=3[va][vb][vc]",
            "[vb]scale=iw/8:ih/8,boxblur=12:2,scale=" + f"{W}:{H},eq=brightness=-0.12[bg]",
            # coins arrondis appliqués à taille fixe PUIS réduction : les filtres d'alpha (alphamerge, geq)
            # ne supportent pas une image dont la taille change à chaque frame
            "[va]format=yuva420p[vaa]", f"[{mask_in}:v]format=gray[vm]", "[vaa][vm]alphamerge[vr]",
            f"[vr]scale={size}[vs]",
            f"[bg][vs]overlay=x='(W-w)/2':y='H-h-{lift}':eval=frame[lay]",
            f"[vc][lay]overlay=0:0:enable='{on}'[vl]"]


def cmd_render(a):
    check_env()
    wd = Path(a.workdir).resolve()
    meta = load(wd / "meta.json") or die(f"{wd} : lance d'abord « pipeline.py prepare »")
    meta["_wd"] = str(wd)
    plan_p = wd / ("plan.auto.json" if a.auto else "plan.json")
    plan = load(plan_p) or die(f"{plan_p.name} absent : écris-le (voir brief.txt) ou utilise --auto")
    if getattr(a, "all_variants", False):  # version principale puis une vidéo par variante d'accroche
        for name in [None] + list(plan.get("variants", {})):
            a.variant, a.all_variants = name, False
            cmd_render(a)
        return
    suffix = ""
    if getattr(a, "variant", None):  # variante d'accroche : surcharge des clés du plan (+ hook_text = texte du hook)
        v = plan.get("variants", {}).get(a.variant) or die(f"variante « {a.variant} » absente de plan.json")
        plan = {**plan, **{k: val for k, val in v.items() if k != "hook_text"}}
        if "hook_text" in v:
            plan["events"] = [{**e, "text": v["hook_text"]} if e.get("fx") == "hook" else e for e in plan["events"]]
        suffix = "_" + a.variant
        log(f"Variante {a.variant}")
    effects = load(ENGINE / "effects.json")["effects"]
    D = load(ROOT / "triggers.json")["defaults"]
    W, H = out_size(meta["width"], meta["height"])

    edit = derush.build(load(wd / "transcript.json"), plan.get("cut", []), plan.get("restore", []),
                        audio16k(wd, meta["video"]), FPS, plan.get("trim", []), plan.get("tail", derush.TAIL),
                        plan.get("head", 0.0), plan.get("intro"), plan.get("cold_open"))
    save(wd / "edit.json", edit)
    for err in edit.get("errors", []):
        log(f"    [!] {err}")
    if not edit["segments"]:
        die("Rien à garder après dérushage (vérifie cut/restore).")
    words = edit["words"]
    cap_words, fix_errors = apply_fixes(words, plan.get("fix", []))
    events, errors = resolve_events(plan, edit, words, effects)
    # geste filmé (head / intro) : c'est l'accroche jouée par la personne, on ne la recouvre jamais. Un élément
    # plein écran prévu à l'ouverture arrive juste après le geste ; le texte d'accroche reste dès la 1re image.
    gesture = (float(plan["intro"][1]) - float(plan["intro"][0])) if plan.get("intro") else float(plan.get("head") or 0)
    if gesture > 0:
        for e in events:
            if e["t"] < 0.05 and e["fx"] in ("number", "percent", "scene", "screen", "chart", "blob", "title"):
                e["t"] = round(gesture, 3)
        add_counts(events)  # le compteur d'un chiffre décalé repart avec lui
    if edit.get("cold_end"):  # fin du flash-forward : flash + whoosh, la vidéo « repart » du début
        events.append({"fx": "flash", "t": round(edit["cold_end"] - 0.05, 3), "dur": 0.3, "params": {}, "sfx": "transitions/fast_woosh"})
        events.sort(key=lambda x: x["t"])
    if plan.get("hook_shake") and not plan.get("hook_sfx"):
        plan["hook_sfx"] = "impacts/hit"
    if plan.get("hook_glitch") and not plan.get("hook_sfx"):
        plan["hook_sfx"] = "transitions/glitch"
    if plan.get("hook_sfx"):  # son marquant sur la toute première image (hook sonore)
        kind = "glitch" if plan.get("hook_glitch") else "shake" if plan.get("hook_shake") else "punch" if plan.get("hook_punch") else "hook"
        events.append({"fx": "hook_sfx", "t": 0.0, "dur": 0, "params": {"kind": kind}, "sfx": plan["hook_sfx"]})
    errors += fix_errors
    errors += show_check(events)
    add_counts(events)
    if not a.auto:  # le storyboard force à lire le sens de chaque phrase avant de placer des effets
        told = {x.get("at") for x in plan.get("story", [])}
        missing = [p["id"] for p in edit["phrases"] if p["kept"] and p["start"] is not None and p["id"] not in told]
        if missing:
            errors.append(f"storyboard absent pour {', '.join(missing)} : ajoute-les dans « story » (voir SKILL.md, Lire le sens)")
        no_illu = [x.get("at") for x in plan.get("story", []) if x.get("at") != "-" and "illu" not in x]
        if no_illu:
            errors.append(f"story sans « illu » pour {', '.join(no_illu)} : décide pour chaque phrase s'il faut une illustration (ou « non »)")
    for err in errors:
        log(f"    [!] {err}")
    platform = plan.get("platform", "all")
    if platform not in PLATFORMS:
        log(f"    [!] platform « {platform} » inconnue (tiktok, reels, shorts, all) : all utilisé")
        platform = "all"
    zn, face_y = zones(meta, W, H, plan.get("mirror") is True, platform)
    dur = round(edit["duration"], 3)

    # 1. calque d'animations transparent (HyperFrames)
    log(f"1/3 Animations : {len(events)} effet(s), {dur:.1f}s...")
    ov = wd / "overlay"
    if ov.exists():
        shutil.rmtree(ov)
    ov.mkdir()
    shutil.copytree(ENGINE / "vendor", ov / "vendor")
    shutil.copytree(ENGINE / "fonts", ov / "fonts")
    shutil.copytree(ROOT / "library" / "emoji", ov / "emoji")
    for err in attach_logos(events, ov) + attach_captures(wd, events, ov):
        log(f"    [!] {err}")
    data = {"W": W, "H": H, "zones": zn, "style": {"accent": plan.get("accent", "#FFE600"),
            "active": plan.get("active", "#FFE600"), "theme": plan.get("theme", "light"), "capSize": plan.get("caption_size", CAP_SIZE)},
            "captions": caption_groups(cap_words, events) if plan.get("captions", True) else [],
            "events": [e for e in events if e["fx"] in OVERLAY_FX],
            "strike_at": STRIKE_AT, "strike_draw": STRIKE_DRAW, "safe": PLATFORMS[platform], "platform": platform,
            "layout": {"windows": list_windows(events, PLATFORMS[platform]["top"]), "scale": LIST_SCALE, "margin": LIST_MARGIN * H, "radius": LIST_RADIUS * W,
                       # sous-titres en bas : vidéo rétrécie, ou site plein écran (le haut est occupé par la page)
                       "low": [w[:2] for w in list_windows(events, PLATFORMS[platform]["top"])] + [(e["t"], e["t"] + e["dur"]) for e in events
                                                      if e["fx"] in ("title", "number", "percent")
                                                      or (e["fx"] == "screen" and e["params"].get("mode") == "full")]}}
    save(wd / f"overlay_plan{suffix}.json", data)  # la planche de contrôle relit celui de la version principale
    html = (ENGINE / "template.html").read_text("utf-8")
    for k, v in {"__W__": W, "__H__": H, "__DUR__": dur, "/*PLAN*/null": json.dumps(data, ensure_ascii=False),
                 "/*EFFECTS*/": (ENGINE / "effects.js").read_text("utf-8")}.items():
        html = html.replace(k, str(v))
    (ov / "index.html").write_text(html, "utf-8")
    ov_mov = wd / "overlay.mov"
    run(["npx", "-y", HYPERFRAMES, "render", ov, "--format", "mov", "-o", ov_mov, "--fps", FPS,
         "--quality", "draft" if a.draft else "looks", "--quiet"], "rendu HyperFrames",
        timeout=max(300, dur * 20))  # un rendu normal prend ~2-4 s par seconde de vidéo

    # 2. coupes : un segment à la fois (un seul gros filtre sur une source 3K sature la mémoire),
    #    vidéo au nombre d'images exact, audio coupé à l'échantillon près sur la même grille
    log(f"2/3 Coupes ({len(edit['segments'])} segment(s))...")
    W2, H2 = int(W * 1.25) // 2 * 2, int(H * 1.25) // 2 * 2
    video_cut = cut_video(wd, meta["video"], edit, W2, H2, mirrored(edit, plan.get("mirror", False)))
    voice = cut_audio(wd, meta["video"], edit)

    # 3. assemblage : zooms + calque d'animations + voix normalisée + SFX
    log("3/3 Assemblage...")
    sfx = pick_sfx(events, effects, D) + counter_sfx(wd, events, D)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", video_cut, "-i", ov_mov, "-i", voice]
    for s in sfx:
        cmd += ["-i", s["file"]]
    mask_in = 3 + len(sfx)
    cmd += ["-framerate", FPS, "-loop", "1", "-i", round_mask(wd, W, H)]
    z = zoom_expr(edit, events, plan.get("cut_zoom", D["cut_zoom"]), plan.get("hook_punch"))
    # secousse d'impact (hook_shake) : tremblement qui s'amortit sur 0,5 s, avec un léger zoom pour avoir de la marge
    shake = float(plan.get("hook_shake") or 0)
    jx = f"+{shake * 0.035:.4f}*iw*sin(it*57)*max(0,1-it/0.5)" if shake else ""
    jy = f"+{shake * 0.025:.4f}*ih*sin(it*43+1)*max(0,1-it/0.5)" if shake else ""
    if shake:
        z = f"{z}+{0.08 * shake:.3f}*max(0,1-it/0.5)"
    # glitch (hook_glitch) : couleurs décalées et parasites sur les premières images, puis l'image se stabilise
    glitch = (",rgbashift=rh=-14:bh=14:gv=6:enable='lt(t,0.3)',noise=alls=35:allf=t:enable='lt(t,0.22)',"
              "eq=contrast=1.35:saturation=1.6:enable='between(t,0.08,0.16)'") if plan.get("hook_glitch") else ""
    f = [f"[0:v]zoompan=z='{z}':x='clip((iw-iw/zoom)/2{jx},0,iw-iw/zoom)':y='clip({face_y:.3f}*ih-ih/zoom/2{jy},0,ih-ih/zoom)'"
         f":d=1:s={W}x{H}:fps={FPS}{glitch}[vz]",
         *layout_filter(events, W, H, mask_in, PLATFORMS[platform]["top"]),
         "[1:v]setpts=PTS-STARTPTS[ov];[vl][ov]overlay=0:0:eof_action=pass:format=auto,format=yuv420p[vout]",
         f"[2:a]{VOICE_NORM},aresample=48000[voice]"]
    sfx_gains(sfx, voice, D, plan.get("sfx_volume_db", 0))
    log("    sons : " + ", ".join(f"{Path(s['file']).stem} {s['gain']:+.0f} dB" for s in sfx))
    mix = "[voice]"
    for k, s in enumerate(sfx):
        # l'attaque du son tombe pile sur l'image : on retire le silence de début propre à chaque fichier
        cut0 = max(0.0, s.get("onset", 0) - s["t"])  # son à t≈0 : on coupe ce qui précéderait le début de la vidéo
        ms = int(max(s["t"] - s.get("onset", 0), 0) * 1000)
        trim = f"atrim=start={cut0:.3f},asetpts=PTS-STARTPTS," if cut0 > 0 else ""
        if s.get("dur"):  # son coupé à la durée de l'action (frappe), à partir de son attaque, fondu court
            end = s.get("onset", 0) - cut0 + s["dur"]
            fade = min(0.25, s["dur"] * 0.4)  # fondu proportionné : pas de coupe sèche, pas de traîne
            trim += f"atrim=0:{end + 0.02:.3f},afade=t=out:st={max(0, end - fade):.3f}:d={fade:.3f},"
        f.append(f"[{3 + k}:a]aresample=48000,{trim}volume={s['gain']}dB,adelay={ms}:all=1[s{k}]")
        mix += f"[s{k}]"
    f.append(f"{mix}amix=inputs={len(sfx) + 1}:normalize=0:duration=first,alimiter=limit=0.95,"
             f"apad,atrim=end_sample={edit['frames'] * 1600}[aout]")
    out = final_path(wd, suffix)
    cmd += ["-filter_complex", ";".join(f), "-map", "[vout]", "-map", "[aout]", "-frames:v", edit["frames"],
            "-c:v", "libx264", "-preset", "veryfast" if a.draft else "medium", "-crf", "23" if a.draft else "18",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
    (wd / "assemble_cmd.txt").write_text(" ".join(f"'{c}'" for c in map(str, cmd)), "utf-8")  # diagnostic
    run(cmd, "ffmpeg")
    if not suffix:
        record_hooks(wd, plan)
    sync = check_sync(out, edit)
    if not a.draft:
        clean_workdir(wd)
    log(f"\nOK -> {out}  ({dur:.1f}s, {len(events)} effet(s), {len(sfx)} son(s)){sync}")


def mirrored(edit, mirror):
    """indices des segments à retourner : plan.mirror = true (tout) ou liste d'ids de phrases
    (ex : un geste vers le bouton « s'abonner » filmé sans le mode miroir)"""
    if mirror is True:
        return set(range(len(edit["segments"])))
    ph = [p for p in edit["phrases"] if p["id"] in (mirror or [])]
    return {k for k, s in enumerate(edit["segments"])
            if any(s["src_start"] < p["src_end"] and s["src_end"] > p["src_start"] for p in ph)}


def cut_video(wd, video, edit, W2, H2, flip=()):
    """chaque segment réencodé séparément avec exactement `frames` images, puis concat sans réencodage"""
    from concurrent.futures import ThreadPoolExecutor
    d = wd / "segments"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()

    def one(k):
        s = edit["segments"][k]
        dst = d / f"{k:03d}.mp4"
        # tpad : si la source se termine avant, on fige la dernière image plutôt que de perdre des images
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{s['src_start']:.4f}", "-i", video, "-an",
             "-vf", f"fps={FPS},scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W2}:{H2},setsar=1,"
                    f"tpad=stop_mode=clone:stop={FPS}" + (",hflip" if k in flip else ""),
             "-frames:v", s["frames"], "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12",
             "-pix_fmt", "yuv420p", "-r", FPS, dst], f"coupe du segment {k + 1}")
        return dst

    with ThreadPoolExecutor(max_workers=3) as ex:
        parts = list(ex.map(one, range(len(edit["segments"]))))
    lst = d / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts), "utf-8")
    out = wd / "video_cut.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], "concat")
    return out


def cut_audio(wd, video, edit):
    """audio coupé à l'échantillon près : chaque morceau dure exactement frames/FPS s, fondu de 12 ms"""
    import wave
    import numpy as np
    src = wd / "audio48k.wav"
    if not src.exists():
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vn", "-ac", "2", "-ar", "48000",
             "-af", "aresample=async=1:first_pts=0", "-c:a", "pcm_s16le", src], "extraction audio")
    with wave.open(str(src)) as f:
        x = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).reshape(-1, 2)
    spf = 48000 // FPS  # 1600 échantillons par image
    fade = int(48000 * 0.012)
    ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
    parts = []
    for s in edit["segments"]:
        a0, n = round(s["src_start"] * 48000), s["frames"] * spf
        p = x[a0:a0 + n].astype(np.float32)
        if len(p) < n:
            p = np.vstack([p, np.zeros((n - len(p), 2), np.float32)])
        p[:fade] *= ramp
        p[-fade:] *= ramp[::-1]
        parts.append(p)
    out = wd / "voice.wav"
    with wave.open(str(out), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(48000)
        f.writeframes(np.clip(np.vstack(parts), -32768, 32767).astype(np.int16).tobytes())
    return out


def check_sync(out, edit):
    r = run(["ffprobe", "-v", "error", "-count_packets", "-show_entries", "stream=codec_type,nb_read_packets,duration",
             "-of", "json", out], "ffprobe")
    st = {s["codec_type"]: s for s in json.loads(r.stdout)["streams"]}
    nv = int(st["video"]["nb_read_packets"])
    da = float(st["audio"].get("duration", 0))
    drift = abs(da - nv / FPS)
    if nv != edit["frames"] or drift > 1.5 / FPS:
        return f"\n[!] synchro à vérifier : {nv} images (attendu {edit['frames']}), audio {da:.3f}s / vidéo {nv / FPS:.3f}s"
    return f"  synchro OK ({nv} images)"


def cmd_verify(a):
    """retranscrit le montage et liste les mots attendus qui manquent (mots amputés aux coupes)"""
    from difflib import SequenceMatcher
    wd = Path(a.workdir).resolve()
    edit, tr = load(wd / "edit.json"), load(wd / "transcript.json")
    out = final_path(wd)
    vp = wd / "verify.json"
    log("Retranscription du montage...")
    run([sys.executable, ROOT / "scripts/transcribe.py", out, "--out", vp, "--model", a.model,
         "--lang", tr.get("language", "fr")], "transcription")
    exp = display_words(edit["words"])
    got = display_words([dict(w, phrase=0) for s in load(vp)["segments"] for w in s.get("words", [])])
    e_t = [(toks(w["word"]) or [""])[0] for w in exp]
    g_t = [(toks(w["word"]) or [""])[0] for w in got]
    sm = SequenceMatcher(None, e_t, g_t, autojunk=False)
    issues = []
    for op, i0, i1, j0, j1 in sm.get_opcodes():
        if op in ("delete", "replace"):
            ctx = " ".join(w["word"] for w in exp[max(i0 - 2, 0):i1 + 2])
            heard = " ".join(w["word"] for w in got[j0:j1])
            issues.append(f"{exp[i0]['start']:6.2f}s  attendu « {' '.join(w['word'] for w in exp[i0:i1])} »"
                          + (f", entendu « {heard} »" if heard else " : absent") + f"   (… {ctx} …)")
    ratio = sm.ratio()
    log(f"Concordance : {ratio:.0%} ({len(issues)} écart(s))")
    for x in issues:
        log("  " + x)
    log("Un écart près d'une coupe = mot amputé ; ailleurs, souvent une simple variante de transcription.")


def cmd_auto(a):
    cmd_prepare(a)
    a.workdir, a.auto = str(workdir_for(Path(a.video).resolve())), True
    cmd_render(a)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "auto"):
        p = sub.add_parser(name)
        p.add_argument("video")
        p.add_argument("--lang", default=None)
        p.add_argument("--model", default="small")
        p.add_argument("--force", action="store_true", help="refait transcription et visage")
        if name == "auto":
            p.add_argument("--draft", action="store_true")
    p = sub.add_parser("verify", help="retranscrit le montage pour repérer les mots amputés")
    p.add_argument("workdir")
    p.add_argument("--model", default="small")
    p = sub.add_parser("sheet", help="planche de contrôle du rendu (une image par effet, zone libre en rouge)")
    p.add_argument("workdir")
    p = sub.add_parser("shots", help="capture les sites des effets screen pour les vérifier")
    p.add_argument("workdir")
    p = sub.add_parser("render")
    p.add_argument("workdir")
    p.add_argument("--draft", action="store_true", help="rendu rapide, qualité réduite")
    p.add_argument("--auto", action="store_true", help="utilise plan.auto.json")
    p.add_argument("--variant", help="rend seulement cette variante d'accroche (plan.variants)")
    p.add_argument("--all-variants", action="store_true", help="version principale + une vidéo par variante d'accroche")
    a = ap.parse_args()
    {"prepare": cmd_prepare, "render": cmd_render, "auto": cmd_auto, "verify": cmd_verify, "shots": cmd_shots, "sheet": cmd_sheet}[a.cmd](a)


if __name__ == "__main__":
    main()
