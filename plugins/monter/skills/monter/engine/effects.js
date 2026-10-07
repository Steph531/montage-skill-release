// effects.js - effets d'incrustation du skill. Lit window.__PLAN__ (écrit par scripts/pipeline.py)
// et construit le DOM + une timeline GSAP en pause pilotée par HyperFrames.
// Ajouter un effet : une fonction dans FX + une entrée dans engine/effects.json.
(function () {
  // on attend les polices avant de construire : sinon les textes sont mesurés avec la police de secours
  // (plus étroite) et débordent une fois Montserrat chargée. HyperFrames attend que window.__timelines soit rempli.
  const FONTS = ["800 40px Montserrat", "900 40px Montserrat", "40px 'Noto Color Emoji'"];
  Promise.all(FONTS.map((f) => document.fonts.load(f))).then(build, build);
  function build() {
  const P = window.__PLAN__;
  const root = document.getElementById("root");
  const tl = gsap.timeline({ paused: true });
  const U = P.H / 1920; // unité : 1 = 1px sur un écran 1080x1920
  const S = P.style;
  // un compte à rebours occupe le coin haut gauche : tout ce qui se pose en haut descend d'autant
  const TIMER_FONT = 46 * U, timerOff = P.events.some((e) => e.fx === "timer") ? TIMER_FONT * 2.1 : 0;
  P.zones.top.y += timerOff;
  root.classList.add("theme-" + (S.theme || "light")); // light : cartes blanches ; glass : cartes sombres translucides
  // haut de la vidéo quand elle est rétrécie (liste, graphique, capture) : le panneau s'arrête au-dessus
  // haut de la vidéo réduite pendant le passage qui contient t (la réduction s'adapte au contenu : pipeline.py list_windows)
  const vTopAt = (t) => {
    const w = P.layout.windows.find(([a, b]) => t >= a - 0.05 && t < b);
    return P.H * (1 - (w ? w[2] : P.layout.scale)) - (P.layout.margin || 0);
  };
  const vTop = vTopAt(-1);
  // zone libre de l'interface du réseau (pipeline.py PLATFORMS) : les panneaux commencent sous la barre du haut
  const panelTop = P.H * (P.safe.top + 0.01) + timerOff;
  // éléments plein écran (title, number, percent, blob) : centrés dans l'espace libre entre la barre du haut de l'appli
  // et les sous-titres abaissés, pour ne jamais les chevaucher
  const lowCapY = P.H * (P.safe.bottom - 0.01) - P.zones.cap.h;
  const fullCenter = (panelTop + lowCapY) / 2, fullRoom = lowCapY - panelTop;
  // à l'ouverture (t < 0,1 s), le texte d'accroche occupe le haut : l'élément se centre dessous
  const openCenter = (P.zones.top.y + P.H * 0.15 + lowCapY) / 2;
  const centerFor = (e) => (e.t < 0.1 ? openCenter : fullCenter);
  const atStart = (e) => e.t < 0.05; // hook visuel : l'élément doit être complet dès la 1re image (miniature)

  function make(cls, html, fontPx) {
    const d = document.createElement("div");
    d.className = "fx " + cls;
    d.innerHTML = html;
    if (fontPx) d.style.fontSize = fontPx + "px";
    root.appendChild(d);
    return d;
  }

  // réduit la police si l'élément dépasse la largeur autorisée
  function fit(el, maxW) {
    const w = el.offsetWidth * 1.08; // marge : la police peut ne pas être encore chargée
    if (w > maxW) el.style.fontSize = parseFloat(el.style.fontSize) * (maxW / w) + "px";
  }

  // place un élément au centre de la zone haute, centré horizontalement
  function placeTop(el) {
    el.style.top = P.zones.top.y + P.zones.top.h / 2 + "px";
    gsap.set(el, { xPercent: -50, yPercent: -50 });
  }

  function show(el, t) { tl.set(el, { visibility: "visible" }, t); }
  function hide(el, t, d = 0.22) {
    tl.to(el, { autoAlpha: 0, scale: 0.9, duration: d, ease: "power2.in" }, t - d);
  }

  const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);

  // nombre qui défile de 0 à sa valeur ("10 000 €", "87 %", "x3") dans l'élément el
  function countUp(el, raw, t, dur) {
    const m = String(raw).match(/^(\D*?)(\d(?:[\d\s.,]*\d)?)(.*)$/); // l'espace avant l'unité reste dans le suffixe
    if (!m) { el.textContent = raw; return; }
    const target = parseFloat(m[2].replace(/\s/g, "").replace(",", "."));
    const dec = (m[2].split(/[.,]/)[1] || "").length, o = { v: 0 };
    const fmt = (v) => m[1] + v.toLocaleString("fr-FR", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + m[3];
    el.textContent = fmt(0);
    tl.to(o, { v: target, duration: dur, ease: "power2.out", onUpdate: () => { el.textContent = fmt(o.v); } }, t);
  }

  // fond assombri plein écran (title, number)
  function backdrop(t, dur, alpha = 0.62) {
    const bg = make("backdrop", "");
    show(bg, t);
    tl.fromTo(bg, { autoAlpha: 0 }, { autoAlpha: alpha, duration: 0.25 }, t);
    tl.to(bg, { autoAlpha: 0, duration: 0.25 }, t + dur - 0.25);
  }

  // ---- briques de motion design communes ----

  // emojis 3D (library/emoji, Fluent UI Emoji, MIT) : par nom, ou par caractère pour les anciens plans
  const GLYPH = { "🚀": "rocket", "🔥": "fire", "💡": "idea", "⚠️": "warning", "⚠": "warning", "✅": "check", "❌": "cross", "💰": "money",
    "📈": "up", "📉": "down", "⏱️": "time", "⏱": "time", "🧠": "brain", "🤔": "thinking", "🤯": "mindblown", "😱": "shock", "🤩": "wow",
    "🎉": "party", "👀": "eyes", "💻": "laptop", "🤖": "robot", "❓": "question" };
  const EMO = new Set(Object.values(GLYPH));
  function emo(x) {
    if (/^logos\//.test(x || "")) return `<img class="emo logo" src="${x}">`; // logo de marque (pipeline.py attach_logos)
    const n = EMO.has(x) ? x : GLYPH[x];
    return n ? `<img class="emo" src="emoji/${n}.png">` : `<span class="emo">${esc(x)}</span>`;
  }

  // texte riche : *mots* = surlignés au marqueur (couleur d'accent), le reste échappé
  function rich(text) {
    // les mots marqués consécutifs forment UN seul trait de marqueur
    let on = false;
    // typographie française : espace insécable avant ? ! : ; » et après « (le « ? » ne part pas seul à la ligne)
    text = String(text ?? "").replace(/\s+([?!:;»])/g, "\u00a0$1").replace(/«\s+/g, "«\u00a0");
    const toks = text.split(/ +/).filter(Boolean).map((w) => {
      const open = w.startsWith("*"), close = /.\*[^\p{L}\d]*$/u.test(w) || (on && w === "*");
      const a = on || open; on = a && !close;
      return { t: esc(w.replace(/\*/g, "")), a };
    });
    const out = [];
    for (const x of toks) {
      const last = out[out.length - 1];
      if (x.a && last && last.a) last.t += " " + x.t; else out.push({ ...x });
    }
    return out.map((x) => x.a ? `<span class="mk"><em style="background:${S.accent}"></em>${x.t}</span>` : x.t).join(" ");
  }


  // coup de surligneur : le fond d'accent passe de gauche à droite derrière chaque mot marqué
  function markers(el, t, now = false) {
    el.querySelectorAll(".mk").forEach((m, i) => {
      const bar = m.querySelector("em");
      if (now) { gsap.set(bar, { scaleX: 1 }); gsap.set(m, { color: "#111" }); return; } // visible dès la 1re image (miniature)
      tl.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: 0.3, ease: "power3.out" }, t + i * 0.08);
      tl.set(m, { color: "#111" }, t + i * 0.08 + 0.12);
    });
  }

  // entrée / sortie des blocs : léger grossissement + fondu, sans rebond « cartoon »
  function enter(el, t) {
    show(el, t);
    tl.fromTo(el, { autoAlpha: 0, scale: 0.92, y: 12 * U }, { autoAlpha: 1, scale: 1, y: 0, duration: 0.35, ease: "power3.out" }, t);
    const im = el.querySelector(".emo");
    if (im) tl.fromTo(im, { scale: 0.3, rotation: -15 }, { scale: 1, rotation: 0, duration: 0.45, ease: "back.out(2.2)" }, t + 0.05);
  }
  function leave(el, t) { tl.to(el, { autoAlpha: 0, scale: 0.96, y: -8 * U, duration: 0.25, ease: "power2.in" }, t - 0.25); }

  // révélation masquée : le contenu monte de derrière une ligne invisible (au lieu d'un fondu)
  function masked(html) { return `<span class="rv"><span class="rvi">${html}</span></span>`; }
  function reveal(el, t, d = 0.45) {
    el.querySelectorAll(".rvi").forEach((x, i) =>
      tl.fromTo(x, { yPercent: 110 }, { yPercent: 0, duration: d, ease: "power4.out" }, t + i * 0.07));
  }
  function unreveal(el, t, d = 0.3) {
    el.querySelectorAll(".rvi").forEach((x) => tl.to(x, { yPercent: -110, duration: d, ease: "power3.in" }, t - d));
  }

  // icônes au trait (grille 24, dessinées pour le skill) : tracées au trait quand elles apparaissent
  const PATHS = {
    check: "M5 12.5l4.5 4.5L19 7.5", cross: "M6 6l12 12M18 6L6 18",
    warning: "M12 3L2.5 20h19L12 3z M12 9.5v5 M12 17.5v.01",
    clock: "M21 12a9 9 0 1 1-18 0a9 9 0 1 1 18 0z M12 7.5V12l3 2",
    bulb: "M9 18h6 M10 21h4 M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0 0 12 3z",
    rocket: "M9 15l-3-3c2-6 7-9 13-9 0 6-3 11-9 13z M14.5 9.5v.01 M7 14c-2 0-3 2-3 6 4 0 6-1 6-3",
    lock: "M6 11h12v10H6z M8 11V7a4 4 0 0 1 8 0v4", key: "M11 14.5a3.5 3.5 0 1 1-7 0a3.5 3.5 0 1 1 7 0z M10 12l9-9 M16 6l2.5 2.5 M13.5 8.5l2 2",
    bug: "M8 9h8v6a4 4 0 0 1-8 0z M12 9v10 M9 9a3 3 0 0 1 6 0 M4 11h4 M16 11h4 M4 17l4-1.5 M20 17l-4-1.5",
    code: "M8 7l-5 5 5 5 M16 7l5 5-5 5 M14 4l-4 16", chat: "M4 5h16v11H9l-5 4z",
    bell: "M6 17v-6a6 6 0 0 1 12 0v6l2 2H4z M10 21h4", up: "M3 17l6-6 4 4 8-8 M15 7h6v6", down: "M3 7l6 6 4-4 8 8 M15 17h6v-6",
    money: "M3 6h18v12H3z M15 12a3 3 0 1 1-6 0a3 3 0 1 1 6 0z M6 9v.01 M18 15v.01",
    eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z M15 12a3 3 0 1 1-6 0a3 3 0 1 1 6 0z",
    fire: "M12 3c1 4 6 6 6 11a6 6 0 0 1-12 0c0-3 2-5 3-6 0 2 1 3 2 3 0-3-1-5 1-8z",
    star: "M12 3l2.8 5.8 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.3l1-6.2L3 9.7l6.2-.9z",
    heart: "M12 20s-8-5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 9c0 6-8 11-8 11z",
    plus: "M12 5v14 M5 12h14", arrow: "M5 12h14 M13 6l6 6-6 6", video: "M3 6h12v12H3z M15 10l6-3v10l-6-3",
    user: "M16 8a4 4 0 1 1-8 0a4 4 0 1 1 8 0z M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5",
    users: "M13 8a3.5 3.5 0 1 1-7 0a3.5 3.5 0 1 1 7 0z M2.5 20c0-3.5 3-5.5 7-5.5s7 2 7 5.5 M15.5 4.6a3.5 3.5 0 0 1 0 6.8 M18 14.8c2.2.6 3.5 2.4 3.5 5.2",
    file: "M6 3h8l4 4v14H6z M14 3v4h4 M9 12h6 M9 16h6", gear: "M15 12a3 3 0 1 1-6 0a3 3 0 1 1 6 0z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M4.9 4.9l2.1 2.1 M17 17l2.1 2.1 M4.9 19.1L7 17 M17 7l2.1-2.1",
    search: "M17 11a6 6 0 1 1-12 0a6 6 0 1 1 12 0z M15.5 15.5L21 21", scissors: "M9 7a3 3 0 1 1-6 0a3 3 0 1 1 6 0z M9 17a3 3 0 1 1-6 0a3 3 0 1 1 6 0z M8.2 8.8L20 18 M8.2 15.2L20 6",
    zoom: "M17 11a6 6 0 1 1-12 0a6 6 0 1 1 12 0z M15.5 15.5L21 21 M11 8v6 M8 11h6", text: "M5 6h14 M12 6v13 M9 19h6",
    shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z M9 12l2 2 4-4", target: "M21 12a9 9 0 1 1-18 0a9 9 0 1 1 18 0z M16 12a4 4 0 1 1-8 0a4 4 0 1 1 8 0z M12 12v.01",
    link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1 M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
    agent: "M5 9h14v10H5z M12 5v4 M12 5a1 1 0 1 0 0-.01 M9 13.5v.01 M15 13.5v.01 M9.5 16.5h5 M3 13v2 M21 13v2",
    flow: "M3 6h6v4H3z M15 14h6v4h-6z M9 8h3a3 3 0 0 1 3 3v3",
  };
  const EMO2ICON = { robot: "agent", brain: "user", laptop: "code", time: "clock", eyes: "eye", check: "check", cross: "cross", idea: "bulb",
    rocket: "rocket", warning: "warning", money: "money", up: "up", down: "down", fire: "fire" };
  const NEG = new Set(["cross", "warning", "bug", "down"]); // icônes « problème » : rouge
  function icon(name, color) {
    const d = PATHS[name] || PATHS.star;
    const c = color || (NEG.has(name) ? "#ef4444" : S.accent);
    return `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="${c}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">` +
      d.split(/ (?=M)/).map((x) => `<path d="${x}" pathLength="1"/>`).join("") + `</svg>`;
  }
  function draw(el, t, d = 0.45) {
    el.querySelectorAll(".ico path").forEach((x, i) =>
      tl.fromTo(x, { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: d, ease: "power2.inOut" }, t + i * 0.08));
  }

  // hauteur (fraction de l'écran) des boutons du rail de droite, communs à TikTok, Reels et Shorts à peu près
  // appel à l'action sans flèche (platform « all ») : bloc centré en haut qui pulse doucement
  function ctaPlain(e) {
    const txt = String(e.params.text || "Abonne-toi"), n = txt.replace(/\*/g, "").length;
    const el = make("cta", `<span class="bx">${masked(rich(txt))}</span>`, Math.min(66 * U, (P.W * 0.84) / (n * 0.6 + 1.6)));
    Object.assign(el.style, { top: P.zones.top.y + "px", left: "50%" });
    gsap.set(el, { xPercent: -50 });
    enter(el, e.t);
    reveal(el, e.t + 0.08);
    markers(el, e.t + 0.3);
    tl.to(el.querySelector(".bx"), { scale: 1.05, duration: 0.35, yoyo: true, repeat: Math.max(1, Math.floor((e.dur - 1) / 0.35)), ease: "sine.inOut" }, e.t + 0.6);
    leave(el, e.t + e.dur);
  }

  // ---- effets fluides : filtre « gooey » (les formes proches fusionnent comme du liquide) ----
  let gooN = 0;
  function gooFilter(blur = 18) {
    const id = "goo" + gooN++;
    return { id, def: `<defs><filter id="${id}" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur in="SourceGraphic" stdDeviation="${blur}"/>` +
      `<feColorMatrix values="1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 28 -11"/></filter></defs>` };
  }
  // hasard reproductible (même rendu à chaque fois)
  function rnd(seed) { let x = Math.floor(seed * 9301 + 49297) % 233280; return () => (x = (x * 9301 + 49297) % 233280) / 233280; }

  // éclaboussure d'impact autour d'un point : traits qui rayonnent + gouttelettes projetées qui fusionnent
  function burst(cx, cy, t, size = 1) {
    const R = 150 * U * size, r = rnd(t * 1000), g = gooFilter(10 * U);
    const lines = Array.from({ length: 10 }, (_, i) => {
      const a = (i / 10) * Math.PI * 2 + r() * 0.3, r0 = R * 0.95, r1 = R * (1.25 + r() * 0.35);
      return `<path d="M${cx + r0 * Math.cos(a)} ${cy + r0 * Math.sin(a)}L${cx + r1 * Math.cos(a)} ${cy + r1 * Math.sin(a)}" pathLength="1"/>`;
    }).join("");
    const drops = Array.from({ length: 9 }, () => {
      const a = r() * Math.PI * 2, d = R * (1.1 + r() * 0.7), rr = (10 + r() * 16) * U;
      return `<circle cx="${cx}" cy="${cy}" r="${rr}" data-x="${d * Math.cos(a)}" data-y="${d * Math.sin(a)}"/>`;
    }).join("");
    const el = make("burst", `<svg viewBox="0 0 ${P.W} ${P.H}">${g.def}` +
      `<g fill="none" stroke="${S.accent}" stroke-width="${9 * U}" stroke-linecap="round">${lines}</g>` +
      `<g fill="${S.accent}" filter="url(#${g.id})">${drops}</g></svg>`);
    show(el, t);
    tl.set(el, { autoAlpha: 1 }, t);
    el.querySelectorAll("path").forEach((p) => {
      tl.fromTo(p, { strokeDasharray: "1 1", strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.18, ease: "power2.out" }, t);
      tl.to(p, { strokeDashoffset: -1, duration: 0.22, ease: "power2.in" }, t + 0.18);
    });
    el.querySelectorAll("circle").forEach((c) => {
      tl.fromTo(c, { attr: { cx, cy } }, { attr: { cx: cx + +c.dataset.x, cy: cy + +c.dataset.y }, duration: 0.45, ease: "power3.out" }, t);
      tl.to(c, { attr: { r: 0 }, duration: 0.3, ease: "power2.in" }, t + 0.25);
    });
    tl.set(el, { autoAlpha: 0 }, t + 0.6);
  }
  // centre de la zone haute (où se posent card, ✓, emoji…)
  const topCenter = () => [P.W / 2, P.zones.top.y + P.zones.top.h / 2];

  const FX = {
    // carte : bloc propre (thème), texte révélé, emoji optionnel
    card(e) {
      const p = e.params;
      const el = make("card bx", (p.logo || p.emoji ? emo(p.logo || p.emoji) : "") + `<div>${masked(rich(p.text))}` + (p.sub ? `<div>${masked(`<small>${esc(p.sub)}</small>`)}</div>` : "") + `</div>`, 84 * U);
      placeTop(el); fit(el, P.W * 0.88);
      enter(el, e.t);
      reveal(el, e.t + 0.08, 0.4);
      markers(el, e.t + 0.35);
      leave(el, e.t + e.dur);
      if (p.burst) burst(...topCenter(), e.t, 1.3);
    },

    check(e) { pill(e, "check"); },
    cross(e) { pill(e, "cross", true); },

    // icône au trait qui se dessine (remplace l'emoji), légende optionnelle
    icon(e) {
      const p = e.params;
      const el = make("iconfx", icon(p.name) + (p.text ? masked(rich(p.text)) : ""), 64 * U);
      placeTop(el);
      show(el, e.t);
      tl.set(el, { autoAlpha: 1 }, e.t);
      tl.fromTo(el.querySelector(".ico"), { scale: 0.6, rotation: -8 }, { scale: 1, rotation: 0, duration: 0.5, ease: "back.out(2)" }, e.t);
      draw(el, e.t, 0.5);
      if (p.text) { reveal(el, e.t + 0.25); markers(el, e.t + 0.5); unreveal(el, e.t + e.dur); }
      tl.to(el.querySelector(".ico"), { scale: 0.7, autoAlpha: 0, duration: 0.25, ease: "power2.in" }, e.t + e.dur - 0.25);
      tl.set(el, { autoAlpha: 0 }, e.t + e.dur);
    },


    stat(e) {
      const raw = String(e.params.value ?? "");
      const el = make("stat", `<b>${esc(raw)}</b>` + (e.params.label ? `<small>${esc(e.params.label)}</small>` : ""), 170 * U);
      placeTop(el); fit(el, P.W * 0.86);
      show(el, e.t);
      tl.fromTo(el, { autoAlpha: 0, scale: 0.6, y: 40 * U },
        { autoAlpha: 1, scale: 1, y: 0, duration: 0.35, ease: "back.out(2)" }, e.t);
      if (e.count[0]) countUp(el.querySelector("b"), raw, e.count[0].t, e.count[0].d); // minutage : pipeline.py add_counts
      if (e.params.burst) burst(...topCenter(), (e.count[0] ? e.count[0].t + e.count[0].d : e.t + 0.3), 1.2);
      hide(el, e.t + e.dur);
    },

    // emoji 3D : arrive en rebondissant, flotte doucement, repart
    emoji(e) {
      const el = make("emoji", emo(e.params.emoji || "idea"), 240 * U);
      placeTop(el);
      show(el, e.t);
      tl.fromTo(el, { autoAlpha: 0, scale: 0.2, rotation: -20 }, { autoAlpha: 1, scale: 1, rotation: 0, duration: 0.5, ease: "back.out(2.4)" }, e.t);
      tl.to(el, { y: -14 * U, rotation: 4, duration: Math.max(0.3, (e.dur - 0.8) / 2), yoyo: true, repeat: 1, ease: "sine.inOut" }, e.t + 0.5);
      tl.to(el, { autoAlpha: 0, scale: 0.6, duration: 0.25, ease: "power2.in" }, e.t + e.dur - 0.25);
      if (e.params.burst) burst(...topCenter(), e.t + 0.1, 1);
    },

    // appel à l'action : texte révélé + flèche tracée vers le vrai bouton de l'appli (rail de droite TikTok/Reels/Shorts),
    // un anneau pulse sur le bouton. target : follow (défaut), like, comment, save, share
    cta(e) {
      const p = e.params, targets = P.safe.targets;
      if (!targets) { ctaPlain(e); return; } // plusieurs réseaux : les boutons ne sont pas au même endroit, pas de flèche
      const [fx, fy] = targets[p.target] ?? targets.follow;
      const tx = P.W * fx, ty = P.H * fy;
      // texte en haut (au-dessus du visage, loin des sous-titres) ; la flèche longe le bord vers la cible
      // bloc ajusté au texte (une ligne), calé du côté de la cible ; la flèche part SOUS le bloc et longe le bord
      // taille déduite du nombre de caractères et bloc ancré au bord par le CSS : aucune mesure du DOM
      // (la police n'est pas encore chargée quand ce script tourne, les mesures seraient fausses)
      const txt = String(p.text || "Abonne-toi"), n = txt.replace(/\*/g, "").length;
      const fs = Math.min(62 * U, (P.W * 0.84) / (n * 0.6 + 1.6)), left = fx < 0.5;
      const el = make("cta", `<span class="bx">${masked(rich(txt))}</span>`, fs);
      Object.assign(el.style, { top: P.zones.top.y + "px", [left ? "left" : "right"]: P.W * 0.06 + "px" });
      const bh = fs * 1.15 + fs * 0.76; // hauteur du bloc : ligne + padding vertical (.bx 0.38em x 2)
      const ax = left ? P.W * 0.14 : P.W * 0.86;
      const ay = P.zones.top.y + bh + 34 * U;
      const edge = left ? P.W * 0.05 : P.W * 0.97; // la courbe passe près du bord, pas sur le visage
      const ex = tx + (left ? 0 : -P.W * 0.02), ey = ty - P.W * 0.1; // pointe juste au-dessus du bouton
      const mx = edge, my = (ay + ey) / 2;
      const ang = Math.atan2(ey - my, ex - mx), hl = 44 * U;
      const head = [ang + 2.6, ang - 2.6].map((a) => `M${ex} ${ey}L${ex + hl * Math.cos(a)} ${ey + hl * Math.sin(a)}`).join(" ");
      const arrow = make("ctarrow", `<svg viewBox="0 0 ${P.W} ${P.H}" fill="none" stroke="#fff" stroke-width="${12 * U}" stroke-linecap="round" stroke-linejoin="round">` +
        `<path class="shaft" d="M${ax} ${ay}Q${mx} ${my} ${ex} ${ey}" pathLength="1"/><path class="head" d="${head}" pathLength="1"/>` +
        `<circle class="ring" cx="${tx}" cy="${ty}" r="${62 * U}" stroke="${S.accent}" stroke-width="${10 * U}"/></svg>`);
      enter(el, e.t); show(arrow, e.t);
      tl.set(arrow, { autoAlpha: 1 }, e.t);
      reveal(el, e.t + 0.08);
      markers(el, e.t + 0.3);
      tl.fromTo(arrow.querySelector(".shaft"), { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.45, ease: "power2.inOut" }, e.t + 0.25);
      tl.fromTo(arrow.querySelector(".head"), { strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: 0.15, ease: "power2.out" }, e.t + 0.68);
      const ring = arrow.querySelector(".ring");
      gsap.set(ring, { transformOrigin: "50% 50%" }); // GSAP calcule l'origine des éléments SVG lui-même
      for (let t = e.t + 0.75; t < e.t + e.dur - 0.6; t += 0.9)
        tl.fromTo(ring, { scale: 0.6, autoAlpha: 1 }, { scale: 1.5, autoAlpha: 0, duration: 0.8, ease: "power2.out" }, t);
      leave(el, e.t + e.dur);
      tl.to(arrow, { autoAlpha: 0, duration: 0.25 }, e.t + e.dur - 0.25);
    },

    // énumération : panneau dans le haut libéré par la vidéo rétrécie (pipeline.py, layout_filter)
    list(e) {
      const p = e.params, top = vTopAt(e.t);
      const el = make("list", (p.title ? `<h3>${esc(p.title)}</h3>` : "") +
        (p.items || []).map((it) => `<div class="row bx">${emo(it.logo || it.emoji || "check")}${masked(rich(it.text))}</div>`).join(""), 110 * U);
      Object.assign(el.style, { left: P.W * 0.07 + "px", top: panelTop + "px", width: P.W * 0.86 + "px", height: top - panelTop - P.H * 0.02 + "px" });
      const rows = [...el.querySelectorAll(".row")];
      // police réduite si les points ne tiennent pas dans la hauteur du panneau
      // largeur réelle d'une ligne = contenu (scrollWidth, les lignes sont en nowrap) ; marge pour la police pas encore chargée
      const room = top - panelTop - P.H * 0.02, wide = Math.max(1, ...rows.map((r) => r.scrollWidth * 1.15));
      // hauteur mesurée contenu calé en haut : centré, ce qui déborde au-dessus n'entre pas dans scrollHeight
      el.style.justifyContent = "flex-start";
      const k = Math.min(1, room / (el.scrollHeight * 1.05), P.W * 0.86 / wide);
      el.style.justifyContent = "";
      if (k < 1) el.style.fontSize = 110 * U * k + "px"; // part grand et réduit jusqu'à remplir le panneau sans déborder
      show(el, e.t);
      tl.fromTo(el, { autoAlpha: 0, y: -40 * U }, { autoAlpha: 1, y: 0, duration: 0.35, ease: "power2.out" }, e.t);
      if (p.title) tl.fromTo(el.querySelector("h3"), { autoAlpha: 0, scale: 0.7 }, { autoAlpha: 1, scale: 1, duration: 0.3, ease: "back.out(2)" }, e.t + 0.1);
      rows.forEach((r, i) => { // chaque point : le bloc glisse, l'emoji rebondit, le texte se révèle
        const t = p.items[i].t;
        tl.fromTo(r, { autoAlpha: 0, x: -40 * U }, { autoAlpha: 1, x: 0, duration: 0.35, ease: "power3.out" }, t);
        tl.fromTo(r.querySelector(".emo"), { scale: 0.3, rotation: -15 }, { scale: 1, rotation: 0, duration: 0.45, ease: "back.out(2.2)" }, t + 0.05);
        reveal(r, t + 0.08, 0.4);
        markers(r, t + 0.35);
      });
      tl.to(el, { autoAlpha: 0, y: -40 * U, duration: 0.3, ease: "power2.in" }, e.t + e.dur - 0.3);
    },

    // capture de site qui défile dans un cadre de navigateur (engine/capture.mjs) ;
    // split : dans le haut libéré par la vidéo rétrécie ; full : plein écran, sous les sous-titres
    screen(e) {
      const p = e.params, full = p.mode === "full";
      const box = full ? { x: 0, y: 0, w: P.W, h: P.H }
                       : { x: P.W * 0.05, y: panelTop, w: P.W * 0.9, h: vTopAt(e.t) - panelTop - P.H * 0.02 };
      const bar = (full ? 120 : 64) * U;
      const el = make("screen" + (full ? " full" : ""),
        `<div class="bar" style="height:${bar}px"><b></b><b></b><b></b><span>🔒 ${esc(p.domain)}</span></div>` +
        `<div class="view"><img src="${esc(p.img)}"></div>`, (full ? 40 : 30) * U);
      Object.assign(el.style, { left: box.x + "px", top: box.y + "px", width: box.w + "px", height: box.h + "px" });
      if (full) el.querySelector(".bar").style.paddingTop = 36 * U + "px";
      const img = el.querySelector("img"), viewH = box.h - bar;
      const shown = (p.img_h / p.img_w) * box.w; // hauteur affichée de la capture
      const dist = Math.max(0, shown - viewH);
      show(el, e.t);
      if (full) {
        if (e.t < 0.05) tl.set(el, { autoAlpha: 1, y: 0 }, 0); // hook visuel : déjà là sur la 1re image (miniature)
        else tl.fromTo(el, { y: P.H }, { autoAlpha: 1, y: 0, duration: 0.4, ease: "power3.out" }, e.t);
        tl.to(el, { y: P.H, duration: 0.35, ease: "power3.in" }, e.t + e.dur - 0.35); // sortie dans les deux cas
        tl.set(el, { autoAlpha: 0 }, e.t + e.dur);
      } else {
        tl.fromTo(el, { autoAlpha: 0, scale: 0.85, y: -30 * U }, { autoAlpha: 1, scale: 1, y: 0, duration: 0.4, ease: "back.out(1.6)" }, e.t);
        hide(el, e.t + e.dur, 0.3);
      }
      if (p.strike) { // page barrée d'un trait rouge (offre disparue, mauvaise pratique…) : une barre qui s'étire en diagonale
        const vw = box.w, vh = viewH, dx = vw * 0.84, dy = vh * 0.7;
        const st = document.createElement("div");
        st.className = "strike";
        Object.assign(st.style, { left: vw * 0.08 + "px", top: vh * 0.85 + "px", width: Math.hypot(dx, dy) + "px", height: 16 * U + "px",
          marginTop: -8 * U + "px", transform: `rotate(${-Math.atan2(dy, dx)}rad)` });
        el.querySelector(".view").appendChild(st);
        const t = e.t + P.strike_at;
        const d = P.strike_draw; // l'impact sonore (pipeline.py) tombe à t + d, quand le trait a fini de barrer
        tl.fromTo(st, { scaleX: 0 }, { scaleX: 1, duration: d, ease: "power2.in" }, t);
        tl.to(img, { filter: "grayscale(0.85) brightness(0.8)", duration: 0.3 }, t + d * 0.7);
        tl.to(el, { x: 12 * U, duration: 0.05, yoyo: true, repeat: 5 }, t + d);
      }
      // défilement : pause pour lire le haut, puis descente régulière (au plus ~1 écran par seconde)
      const t0 = e.t + 0.7, span = Math.max(0.5, e.dur - 1.2);
      if (p.strike && p.scroll === undefined) p.scroll = false; // une page barrée reste fixe : on lit ce qui est barré
      const d = p.scroll === false ? 0 : Math.min(dist, viewH * span);
      if (d > 0) tl.fromTo(img, { y: 0 }, { y: -d, duration: span, ease: "power1.inOut" }, t0);
    },

    // graphique : barres qui poussent ou courbe qui se trace, dans le haut libéré par la vidéo rétrécie
    chart(e) {
      const p = e.params, data = (p.data || []).filter((d) => isFinite(+d.value));
      if (!data.length) return;
      const top = vTopAt(e.t), unit = p.unit ? String(p.unit) : "";
      const box = { x: P.W * 0.05, y: panelTop, w: P.W * 0.9, h: top - panelTop - P.H * 0.02 };
      const el = make("chart", (p.title ? `<h3>${esc(p.title)}</h3>` : "") + `<div class="plot"></div>`, 40 * U);
      Object.assign(el.style, { left: box.x + "px", top: box.y + "px", width: box.w + "px", height: box.h + "px" });
      const plot = el.querySelector(".plot"), hi = p.highlight ?? data.length - 1;
      const max = Math.max(...data.map((d) => +d.value)) || 1;
      const label = (v) => (+v).toLocaleString("fr-FR") + unit;
      show(el, e.t);
      tl.fromTo(el, { autoAlpha: 0, y: -30 * U }, { autoAlpha: 1, y: 0, duration: 0.35, ease: "power2.out" }, e.t);
      const t0 = e.t + 0.3, grow = Math.min(0.7, e.dur * 0.3), gap = Math.min(0.18, (e.dur * 0.4) / data.length);
      if ((p.kind || "bar") === "bar") {
        plot.innerHTML = data.map((d, i) => `<div class="col${i === hi ? " hi" : ""}"><b></b><div class="bar"></div><span>${esc(d.label)}</span></div>`).join("");
        [...plot.children].forEach((c, i) => {
          const bar = c.querySelector(".bar"), t = t0 + i * gap;
          bar.style.height = Math.max(4, (data[i].value / max) * 100) + "%";
          if (i === hi) bar.style.background = S.accent;
          tl.fromTo(bar, { scaleY: 0 }, { scaleY: 1, duration: grow, ease: "power3.out" }, t);
          tl.fromTo(c.querySelector("b"), { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.2 }, t);
          countUp(c.querySelector("b"), label(data[i].value), e.count[i].t, e.count[i].d);
        });
      } else { // courbe SVG : le tracé se dessine, puis les points et la dernière valeur apparaissent
        const W = 1000, H = 520, pad = 40, n = data.length;
        const min = Math.min(0, ...data.map((d) => +d.value));
        const pts = data.map((d, i) => [pad + (i * (W - 2 * pad)) / Math.max(1, n - 1), H - pad - ((d.value - min) / (max - min || 1)) * (H - 2 * pad)]);
        plot.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none"><path class="area" d="M${pts.map((q) => q.join(",")).join("L")}L${pts[n - 1][0]},${H}L${pts[0][0]},${H}Z" fill="${S.accent}"/><path class="line" d="M${pts.map((q) => q.join(",")).join("L")}" stroke="${S.accent}"/></svg>` +
          `<div class="dots">${pts.map((q, i) => `<i style="left:${(q[0] / W) * 100}%;top:${(q[1] / H) * 100}%"></i>${i === hi ? `<b style="left:${(q[0] / W) * 100}%;top:${(q[1] / H) * 100}%"></b>` : ""}`).join("")}</div>` +
          `<div class="xl">${data.map((d) => `<span>${esc(d.label)}</span>`).join("")}</div>`;
        const line = plot.querySelector(".line"), len = line.getTotalLength();
        gsap.set(line, { strokeDasharray: len, strokeDashoffset: len });
        const draw = Math.min(1.2, e.dur * 0.4);
        tl.to(line, { strokeDashoffset: 0, duration: draw, ease: "power1.inOut" }, t0);
        tl.fromTo(plot.querySelector(".area"), { autoAlpha: 0 }, { autoAlpha: 0.18, duration: draw }, t0);
        plot.querySelectorAll(".dots i").forEach((d, i) =>
          tl.fromTo(d, { scale: 0 }, { scale: 1, duration: 0.25, ease: "back.out(3)" }, t0 + (draw * i) / Math.max(1, n - 1)));
        const v = plot.querySelector(".dots b");
        if (v) { tl.fromTo(v, { autoAlpha: 0, y: 20 * U }, { autoAlpha: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + draw); countUp(v, label(data[hi].value), e.count[0].t, e.count[0].d); }
      }
      hide(el, e.t + e.dur, 0.3);
    },

    // titre plein écran : les mots arrivent un par un, *mot* surligné
    title(e) {
      const p = e.params;
      backdrop(e.t, e.dur);
      // *plusieurs mots* surlignés : chaque mot entre les astérisques est marqué
      let on = false;
      const words = String(p.text || "").split(/\s+/).filter(Boolean).map((w) => {
        // « *l'IA*, » : la ponctuation peut suivre l'astérisque fermant
        const open = w.startsWith("*"), close = /.\*[^\p{L}\d]*$/u.test(w) || (on && /^\*/.test(w) && w.length === 1);
        const a = on || open; on = (on || open) && !close;
        return { w: w.replace(/\*/g, ""), a };
      });
      const el = make("title", (p.logo ? `<img class="tlogo" src="${p.logo}">` : "") + (p.sub ? `<small>${esc(p.sub)}</small>` : "") +
        `<div>${words.map((x) => `<span class="w${x.a ? " a" : ""}"><em></em>${esc(x.w)}</span>`).join(" ")}</div>`, 150 * U);
      Object.assign(el.style, { left: P.W * 0.07 + "px", width: P.W * 0.86 + "px", top: centerFor(e) + "px" });
      gsap.set(el, { yPercent: -50 });
      const widest = Math.max(...[...el.querySelectorAll(".w")].map((w) => w.offsetWidth * 1.08));
      if (widest > P.W * 0.86) el.style.fontSize = 150 * U * (P.W * 0.86 / widest) + "px";
      show(el, e.t);
      tl.set(el, { autoAlpha: 1 }, e.t);
      if (p.sub) tl.fromTo(el.querySelector("small"), { autoAlpha: 0, y: 20 * U }, { autoAlpha: 1, y: 0, duration: 0.3 }, e.t + 0.05);
      if (p.logo) tl.fromTo(el.querySelector(".tlogo"), { autoAlpha: 0, scale: 0.4 }, { autoAlpha: 1, scale: 1, duration: 0.45, ease: "back.out(2.2)" }, e.t);
      el.querySelectorAll(".w").forEach((w, i) => {
        const t = e.t + 0.12 + i * 0.09;
        tl.fromTo(w, { autoAlpha: 0, yPercent: 60, rotation: 4 }, { autoAlpha: 1, yPercent: 0, rotation: 0, duration: 0.4, ease: "back.out(1.7)" }, t);
        if (w.classList.contains("a")) {
          const bar = w.querySelector("em");
          bar.style.background = S.accent;
          tl.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: 0.35, ease: "power3.out" }, t + 0.3);
          tl.set(w, { color: "#111" }, t + 0.42);
        }
      });
      tl.to(el, { autoAlpha: 0, y: -60 * U, duration: 0.25, ease: "power2.in" }, e.t + e.dur - 0.25);
    },

    // grand chiffre plein écran qui défile jusqu'à sa valeur
    number(e) {
      const p = e.params;
      backdrop(e.t, e.dur, 0.7);
      const el = make("number", `<b></b><i></i>` + (p.label ? `<small>${esc(p.label)}</small>` : ""), (atStart(e) ? 210 : 300) * U); // à l'ouverture, plus petit : il partage l'écran avec l'accroche
      Object.assign(el.style, { left: "50%", top: centerFor(e) + (atStart(e) ? P.H * 0.045 : 0) + "px" }); // sous l'accroche
      gsap.set(el, { xPercent: -50, yPercent: -50 });
      const b = el.querySelector("b"), bar = el.querySelector("i");
      b.textContent = String(p.value ?? ""); // largeur finale, pour adapter la taille
      fit(el, P.W * 0.9);
      b.style.color = S.accent; bar.style.background = S.accent;
      show(el, e.t);
      if (atStart(e)) tl.fromTo(el, { autoAlpha: 1, scale: 1.05 }, { scale: 1, duration: 0.35, ease: "power3.out" }, 0);
      else tl.fromTo(el, { autoAlpha: 0, scale: 0.6 }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: "back.out(2)" }, e.t);
      const count = e.count[0] ? e.count[0].d : 0.01;
      if (atStart(e)) b.textContent = String(p.value ?? ""); // à l'ouverture : la valeur finale, pas un « 0 »
      else countUp(b, p.value ?? "", e.t + 0.1, count);
      tl.fromTo(el, { scale: 1 }, { scale: 1.08, duration: 0.12, yoyo: true, repeat: 1, ease: "power2.out" }, e.t + 0.1 + count);
      tl.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: 0.4, ease: "power3.out" }, e.t + 0.1 + count);
      if (p.label) tl.fromTo(el.querySelector("small"), { autoAlpha: 0, y: 20 * U }, { autoAlpha: 1, y: 0, duration: 0.3 }, e.t + 0.2 + count);
      hide(el, e.t + e.dur, 0.25);
      if (p.burst) burst(P.W / 2, centerFor(e), e.t + 0.1 + count, 1.8);
    },

    // pourcentage : un anneau se remplit pendant que le chiffre défile au centre
    percent(e) {
      const p = e.params, v = Math.max(0, Math.min(100, parseFloat(String(p.value).replace(",", ".")) || 0));
      backdrop(e.t, e.dur, 0.7);
      const R = 46, L = 2 * Math.PI * R;
      const el = make("percent", `<div class="ring"><svg viewBox="0 0 100 100"><circle class="track" cx="50" cy="50" r="${R}"/>` +
        `<circle class="arc" cx="50" cy="50" r="${R}" stroke="${S.accent}" stroke-dasharray="${L}" stroke-dashoffset="${L}"/></svg><b></b></div>` +
        (p.label ? `<small>${esc(p.label)}</small>` : ""), 150 * U);
      Object.assign(el.style, { left: "50%", top: centerFor(e) + "px", width: Math.min(P.W * 0.62, fullRoom * 0.7) + "px" });
      gsap.set(el, { xPercent: -50, yPercent: -50 });
      const b = el.querySelector("b"), c = e.count[0] || { t: e.t + 0.1, d: 0.01 };
      const label = /%/.test(String(p.value)) ? String(p.value) : v.toLocaleString("fr-FR") + " %";
      show(el, e.t);
      if (atStart(e)) tl.set(el, { autoAlpha: 1 }, 0);
      else tl.fromTo(el, { autoAlpha: 0, scale: 0.6 }, { autoAlpha: 1, scale: 1, duration: 0.35, ease: "back.out(2)" }, e.t);
      if (!atStart(e)) tl.to(el.querySelector(".arc"), { strokeDashoffset: L * (1 - v / 100), duration: c.d, ease: "power2.out" }, c.t);
      if (atStart(e)) { b.textContent = label; gsap.set(el.querySelector(".arc"), { strokeDashoffset: L * (1 - v / 100) }); }
      else countUp(b, label, c.t, c.d);
      tl.fromTo(el.querySelector(".ring"), { scale: 1 }, { scale: 1.06, duration: 0.12, yoyo: true, repeat: 1, ease: "power2.out" }, c.t + c.d);
      if (p.label) tl.fromTo(el.querySelector("small"), { autoAlpha: 0, y: 20 * U }, { autoAlpha: 1, y: 0, duration: 0.3 }, c.t + c.d + 0.1);
      hide(el, e.t + e.dur, 0.25);
    },

    // hook textuel : visible dès la première image (c'est aussi la miniature), *mots* en couleur
    // hook textuel, 4 styles (à varier d'une vidéo à l'autre) ; toujours complet dès la 1re image (miniature)
    //   block : bloc du thème · bold : grands mots en capitales sur l'image · tag : étiquette + phrase · emoji : emoji 3D + texte
    hook(e) {
      const p = e.params, style = p.style || "block", now = e.t < 0.05;
      let el;
      if (style === "bold") {
        el = make("hook hk-bold", rich(p.text), 92 * U);
        Object.assign(el.style, { left: P.W * 0.07 + "px", width: P.W * 0.86 + "px", top: P.zones.top.y + "px" });
      } else if (style === "tag") {
        el = make("hook hk-tag", `<i style="background:${S.accent}">${esc(p.tag || "À savoir")}</i><span class="bx">${rich(p.text)}</span>`, 64 * U);
        Object.assign(el.style, { left: "50%", top: P.zones.top.y + "px", maxWidth: P.W * 0.88 + "px" });
        gsap.set(el, { xPercent: -50 });
      } else if (style === "emoji") {
        el = make("hook hk-emo bx", emo(p.emoji || "question") + `<span>${rich(p.text)}</span>`, 64 * U);
        Object.assign(el.style, { left: "50%", top: P.zones.top.y + "px", maxWidth: P.W * 0.88 + "px" });
        gsap.set(el, { xPercent: -50 });
      } else {
        el = make("hook bx", rich(p.text), 68 * U);
        Object.assign(el.style, { left: "50%", top: P.zones.top.y + "px", maxWidth: P.W * 0.88 + "px" });
        gsap.set(el, { xPercent: -50 });
      }
      markers(el, e.t, now);
      show(el, e.t);
      tl.set(el, { autoAlpha: 1 }, e.t);
      if (style === "bold") { // les mots tombent un à un… sauf sur la 1re image, où tout est déjà là
        if (!now) el.querySelectorAll(".mk").forEach((m, i) => tl.fromTo(m, { scale: 1.6, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 0.25, ease: "back.out(2)" }, e.t + i * 0.08));
        else tl.fromTo(el, { scale: 1.08 }, { scale: 1, duration: 0.4, ease: "power3.out" }, 0);
      } else if (style === "emoji") {
        tl.fromTo(el.querySelector(".emo"), { rotation: -12 }, { rotation: 8, duration: 0.5, yoyo: true, repeat: 3, ease: "sine.inOut" }, e.t);
      } else if (style === "tag") {
        tl.fromTo(el.querySelector("i"), { scale: 1 }, { scale: 1.08, duration: 0.3, yoyo: true, repeat: 3, ease: "sine.inOut" }, e.t + 0.2);
      } else if (!now) {
        tl.fromTo(el, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.35, ease: "power3.out" }, e.t);
      }
      tl.to(el, { autoAlpha: 0, y: -20 * U, duration: 0.25, ease: "power2.in" }, e.t + e.dur - 0.25);
    },

    // transition liquide plein écran : des gouttes montent, fusionnent, couvrent l'écran (titre optionnel), puis s'en vont par le haut
    splash(e) {
      const p = e.params, r = rnd(e.t * 1000 + 7), g = gooFilter(28 * U), n = 9;
      const layer = (color, delay) => {
        const blobs = Array.from({ length: n }, (_, i) => {
          const rr = P.W * (0.2 + r() * 0.14), x = (i + 0.5) * (P.W / n) + (r() - 0.5) * P.W * 0.06;
          return `<circle cx="${x}" cy="${P.H + rr}" r="${rr}" data-d="${delay + r() * 0.12}"/>`;
        }).join("");
        return `<g fill="${color}" filter="url(#${g.id})"><rect x="0" y="${P.H}" width="${P.W}" height="${P.H * 1.6}" class="body"/>${blobs}</g>`;
      };
      const el = make("splash", `<svg viewBox="0 0 ${P.W} ${P.H}">${g.def}${layer(S.accent, 0)}${layer("#ffffff", 0.1)}</svg>` +
        (p.text ? `<div class="splash-t">${p.sub ? `<small>${esc(p.sub)}</small>` : ""}${masked(rich(p.text))}</div>` : ""), 120 * U);
      const D = e.dur, up = Math.min(0.55, D * 0.4), out = Math.min(0.5, D * 0.35);
      show(el, e.t);
      tl.set(el, { autoAlpha: 1 }, e.t);
      el.querySelectorAll("g").forEach((grp) => {
        const body = grp.querySelector(".body");
        grp.querySelectorAll("circle").forEach((c) => {
          const d = +c.dataset.d, rr = +c.getAttribute("r");
          tl.fromTo(c, { attr: { cy: P.H + rr } }, { attr: { cy: -rr * 0.2 }, duration: up, ease: "power2.in" }, e.t + d);
          tl.to(c, { attr: { cy: -P.H * 0.6 - rr }, duration: out, ease: "power2.in" }, e.t + D - out + d * 0.5);
        });
        const d0 = +grp.querySelector("circle").dataset.d;
        tl.fromTo(body, { attr: { y: P.H } }, { attr: { y: -P.H * 0.1 }, duration: up, ease: "power2.in" }, e.t + d0 + 0.08);
        tl.to(body, { attr: { y: -P.H * 1.8 }, duration: out, ease: "power2.in" }, e.t + D - out + d0 * 0.5);
      });
      if (p.text) {
        const tx = el.querySelector(".splash-t");
        tl.set(tx, { autoAlpha: 0 }, e.t); // le titre n'apparaît qu'une fois l'écran couvert
        tl.set(tx, { autoAlpha: 1 }, e.t + up + 0.05);
        reveal(tx, e.t + up + 0.05, 0.45);
        markers(tx, e.t + up + 0.35);
        tl.to(tx, { autoAlpha: 0, y: -60 * U, duration: 0.25, ease: "power2.in" }, e.t + D - out);
      }
      tl.set(el, { autoAlpha: 0 }, e.t + D + 0.2);
    },

    // forme liquide qui ondule derrière un mot fort (plein écran court)
    blob(e) {
      // à l'ouverture, le texte d'accroche occupe le haut : forme plus petite et un peu plus bas
      const k0 = atStart(e) ? 0.78 : 1;
      const p = e.params, g = gooFilter(24 * U), r = rnd(e.t * 1000 + 3), cx = P.W / 2, cy = centerFor(e) + (atStart(e) ? P.H * 0.04 : 0);
      // forme assez grande pour contenir le texte : 8 gouttes réparties sur une ellipse large
      const circles = Array.from({ length: 8 }, (_, i) => {
        const a = (i / 8) * Math.PI * 2, rx = P.W * 0.26 * k0, ry = P.W * 0.12 * k0;
        return `<circle cx="${cx + Math.cos(a) * rx + (r() - 0.5) * P.W * 0.06 * k0}" cy="${cy + Math.sin(a) * ry}" r="${P.W * (0.19 + r() * 0.06) * k0}"/>`;
      }).join("");
      // taille du texte d'après le nombre de caractères de la ligne la plus longue (2 lignes max, tient dans la forme)
      const words = String(p.text).replace(/\*/g, "").split(/\s+/), half = Math.ceil(words.length / 2);
      const longest = Math.max(words.slice(0, half).join(" ").length, words.slice(half).join(" ").length);
      const fs = Math.min(130 * U, (P.W * 0.66) / (longest * 0.66)) * k0;
      const el = make("blob", `<svg viewBox="0 0 ${P.W} ${P.H}">${g.def}<g fill="${S.accent}" filter="url(#${g.id})">${circles}</g></svg>` +
        `<div class="blob-t">${masked(rich(p.text))}</div>`, fs);
      const tx = el.querySelector(".blob-t");
      tx.style.top = cy + "px";
      show(el, e.t);
      tl.set(el, { autoAlpha: 1 }, e.t);
      el.querySelectorAll("circle").forEach((c, i) => {
        const r0 = +c.getAttribute("r");
        if (atStart(e)) gsap.set(c, { attr: { r: r0 } }); // déjà déployée sur la 1re image
        else tl.fromTo(c, { attr: { r: 0 } }, { attr: { r: r0 }, duration: 0.45, ease: "back.out(1.6)" }, e.t + i * 0.04);
        tl.to(c, { attr: { cx: +c.getAttribute("cx") + (r() - 0.5) * P.W * 0.12, cy: +c.getAttribute("cy") + (r() - 0.5) * P.W * 0.1 },
          duration: e.dur * 0.6, ease: "sine.inOut", yoyo: true, repeat: 1 }, e.t + 0.3);
        tl.to(c, { attr: { r: 0 }, duration: 0.3, ease: "power2.in" }, e.t + e.dur - 0.3 + i * 0.02);
      });
      if (!atStart(e)) reveal(tx, e.t + 0.2, 0.45);
      tl.to(tx, { autoAlpha: 0, scale: 0.9, duration: 0.2 }, e.t + e.dur - 0.3);
      if (p.burst !== false) burst(cx, cy, e.t + 0.15, 1.6);
    },

    // scènes d'illustration générées (pas de rush à fournir) : maquettes d'interface génériques animées,
    // dans le haut libéré par la vidéo rétrécie. kind : code | terminal | chat | compare
    scene(e) {
      const p = e.params, kind = p.kind || "code";
      const full = p.mode === "full"; // full : grande fenêtre sur fond assombri (ouverture), sans rétrécir la vidéo
      const top0 = e.t < 0.1 ? P.zones.top.y + P.H * 0.15 : panelTop;
      const box = full ? { x: P.W * 0.06, y: top0, w: P.W * 0.88, h: lowCapY - top0 - P.H * 0.02 }
                       : { x: P.W * 0.05, y: panelTop, w: P.W * 0.9, h: vTopAt(e.t) - panelTop - P.H * 0.02 };
      if (full) backdrop(e.t, e.dur, 0.55);
      const dark = kind === "code" || kind === "terminal";
      const head = `<div class="sc-bar"><b></b><b></b><b></b><span>${esc(p.title || { code: "app.js", terminal: "Terminal", chat: "Assistant IA", compare: "" }[kind])}</span></div>`;
      const el = make("scene" + (dark ? " dark" : ""), (kind === "compare" ? "" : head) + `<div class="sc-body"></div>`, 30 * U);
      Object.assign(el.style, { left: box.x + "px", top: box.y + "px", width: box.w + "px", height: box.h + "px" });
      const body = el.querySelector(".sc-body"), T0 = e.t + 0.4, span = Math.max(0.6, e.dur - 1.2);
      show(el, e.t);
      if (atStart(e)) tl.set(el, { autoAlpha: 1 }, 0);
      else tl.fromTo(el, { autoAlpha: 0, y: -30 * U, scale: 0.94 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.4, ease: "power3.out" }, e.t);
      // texte tapé caractère par caractère
      const type = (node, text, t, d) => {
        const o = { n: 0 };
        node.textContent = "";
        tl.to(o, { n: text.length, duration: d, ease: "none", onUpdate: () => { node.textContent = text.slice(0, Math.round(o.n)); } }, t);
      };
      if (kind === "code") {
        const lines = p.lines || [], hi = p.highlight || {};
        // taille limitée par la hauteur ET par la ligne la plus longue (police à chasse fixe : ~0.6 em par caractère)
        const longest = Math.max(1, ...lines.map((l) => l.length + 4));
        const fs = Math.min(54 * U, (box.h * 0.8) / ((lines.length + (hi.note ? 2 : 0.5)) * 1.55), (box.w * 0.9) / (longest * 0.62));
        body.style.fontSize = fs + "px";
        body.innerHTML = lines.map((l, i) => `<div class="ln"><i>${i + 1}</i><code></code></div>`).join("") +
          (hi.note ? `<div class="sc-note ${hi.color === "green" ? "ok" : "ko"}">${emo(hi.color === "green" ? "check" : "warning")}<span>${esc(hi.note)}</span></div>` : "");
        const rows = [...body.querySelectorAll(".ln")]; // minutage de frappe : pipeline.py (e.typing), comme le son de clavier
        if (atStart(e)) rows.forEach((r, i) => { r.querySelector("code").textContent = lines[i]; }); // ouverture : code déjà écrit
        else rows.forEach((r, i) => e.typing[i] && type(r.querySelector("code"), lines[i], e.typing[i].t, e.typing[i].d));
        // steps : [{t, line, color?, note?}] : chaque ligne s'allume quand elle est dite, la précédente s'éteint
        (p.steps || []).forEach((st, i) => {
          const r = rows[st.line], prev = i ? rows[p.steps[i - 1].line] : null;
          if (!r) return;
          if (prev && prev !== r) tl.set(prev, { attr: { class: "ln dim" } }, st.t);
          tl.set(r, { attr: { class: "ln hl " + (st.color === "red" ? "ko" : "ok") } }, st.t);
          tl.fromTo(r, { scale: 1 }, { scale: 1.04, duration: 0.12, yoyo: true, repeat: 1, ease: "power2.out", immediateRender: false }, st.t);
          if (st.note) {
            const n = document.createElement("span");
            n.className = "ln-note"; n.textContent = st.note; r.appendChild(n);
            tl.fromTo(n, { autoAlpha: 0, x: -10 * U }, { autoAlpha: 1, x: 0, duration: 0.25, ease: "power3.out" }, st.t + 0.05);
          }
        });
        if (hi.line != null && rows[hi.line]) {
          const t = atStart(e) ? 0.35 : T0 + span * 0.65;
          tl.set(rows[hi.line], { attr: { class: "ln hl " + (hi.color === "green" ? "ok" : "ko") } }, t);
          tl.fromTo(rows[hi.line], { x: 0 }, { x: 8 * U, duration: 0.05, yoyo: true, repeat: 5 }, t);
          const n = body.querySelector(".sc-note");
          if (n) tl.fromTo(n, { autoAlpha: 0, y: 14 * U }, { autoAlpha: 1, y: 0, duration: 0.3, ease: "power3.out" }, t + 0.15);
        }
      } else if (kind === "terminal") {
        const lines = (p.lines || []).map((l) => typeof l === "string" ? { text: l } : l);
        const longest = Math.max(1, ...lines.map((l) => l.text.length + 3));
        const fs = Math.min(50 * U, (box.h * 0.8) / (lines.length * 1.6), (box.w * 0.9) / (longest * 0.62));
        body.style.fontSize = fs + "px";
        body.innerHTML = lines.map((l) => `<div class="tl${l.cmd ? " cmd" : ""}">${l.cmd ? "<i>$</i> " : ""}<code></code></div>`).join("");
        const rows = [...body.querySelectorAll(".tl")];
        let t = atStart(e) ? 0 : T0, k = 0;
        if (atStart(e)) { lines.forEach((l, i) => { rows[i].querySelector("code").textContent = l.text; tl.set(rows[i], { autoAlpha: 1 }, 0); }); lines.length = 0; }
        lines.forEach((l, i) => {
          tl.fromTo(rows[i], { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.05 }, t);
          if (l.cmd && e.typing[k]) { const w = e.typing[k++]; type(rows[i].querySelector("code"), l.text, w.t, w.d); t = w.t + w.d + 0.15; }
          else { rows[i].querySelector("code").textContent = l.text; t += (span * 0.6) / Math.max(1, lines.length); }
        });
      } else if (kind === "chat") {
        const msgs = p.messages || [];
        const fs = Math.min(48 * U, (box.h * 0.8) / (msgs.length * 3.2));
        body.style.fontSize = fs + "px";
        body.innerHTML = msgs.map((m) => `<div class="msg ${m.from === "user" ? "me" : "ai"}"><span>${esc(m.text)}</span><em><b></b><b></b><b></b></em></div>`).join("");
        const rows = [...body.querySelectorAll(".msg")], per = span / Math.max(1, msgs.length);
        rows.forEach((r, i) => {
          if (i === 0 && atStart(e)) { tl.set(r, { autoAlpha: 1 }, 0); return; } // ouverture : la question est déjà là
          const t = T0 + i * per;
          if (msgs[i].from !== "user") { // l'IA « écrit » avant de répondre
            const dots = r.querySelector("em"), txt = r.querySelector("span");
            tl.set(txt, { display: "none" }, e.t); tl.set(dots, { display: "inline-flex" }, e.t);
            tl.fromTo(r, { autoAlpha: 0, y: 16 * U }, { autoAlpha: 1, y: 0, duration: 0.25, ease: "power3.out" }, t);
            dots.querySelectorAll("b").forEach((b, k) => tl.fromTo(b, { y: 0 }, { y: -6 * U, duration: 0.18, yoyo: true, repeat: 3, ease: "sine.inOut" }, t + k * 0.08));
            tl.set(dots, { display: "none" }, t + Math.min(0.7, per * 0.5)); tl.set(txt, { display: "inline" }, t + Math.min(0.7, per * 0.5));
          } else tl.fromTo(r, { autoAlpha: 0, y: 16 * U }, { autoAlpha: 1, y: 0, duration: 0.25, ease: "power3.out" }, t);
        });
      } else { // compare : deux panneaux, l'avant (terne, ✗) puis l'après (✓)
        const a = p.before || {}, b = p.after || {};
        const pane = (x, ok) => `<div class="pane ${ok ? "ok" : "ko"}"><h4>${emo(ok ? "check" : "cross")}${esc(x.label || (ok ? "Après" : "Avant"))}</h4><p>${rich(x.text || "")}</p></div>`;
        body.innerHTML = pane(a, false) + pane(b, true);
        body.style.fontSize = 40 * U + "px";
        const [pa, pb] = body.querySelectorAll(".pane");
        tl.fromTo(pa, { autoAlpha: 0, x: -40 * U }, { autoAlpha: 1, x: 0, duration: 0.35, ease: "power3.out" }, T0);
        tl.fromTo(pb, { autoAlpha: 0, x: 40 * U }, { autoAlpha: 1, x: 0, duration: 0.35, ease: "power3.out" }, T0 + span * 0.4);
        markers(pb, T0 + span * 0.4 + 0.3);
      }
      // garde-fou : le contenu (déjà complet dans le DOM) ne doit jamais dépasser de la fenêtre
      const fsz = () => parseFloat(body.style.fontSize || getComputedStyle(body).fontSize);
      for (let k = 0; k < 12 && body.scrollHeight > body.clientHeight + 1; k++) body.style.fontSize = fsz() * 0.9 + "px";
      tl.to(el, { autoAlpha: 0, y: -20 * U, duration: 0.3, ease: "power2.in" }, e.t + e.dur - 0.3);
    },

    // schéma animé sur un plateau clair : cases (emoji en pastille + texte) qui apparaissent quand elles sont dites,
    // liens courbes qui se tracent (pointillés pour hub), points qui voyagent sur les liens. kind : flow | hub | cycle | tree.
    // item.tone : pos (vert) | neg (rouge) colore le lien et la pastille
    diagram(e) {
      const p = e.params, kind = p.kind || "flow", items = p.items || [];
      if (!items.length) return;
      const TONE = { pos: ["#2f9e7a", "#e2f4ec"], neg: ["#e0603f", "#fbe6df"], hi: ["#c9a400", "#fff3b8"], none: ["#8a93a6", "#eff1f5"] };
      const tone = (i) => TONE[items[i].tone] || (i === p.highlight ? TONE.hi : TONE.none);
      const top = vTopAt(e.t), box = { x: P.W * 0.04, y: panelTop, w: P.W * 0.92, h: top - panelTop - P.H * 0.02 };
      const el = make("diagram", (p.title ? `<h3><span>${esc(p.title)}</span></h3>` : "") + `<div class="dg"><svg></svg></div>`, 34 * U);
      Object.assign(el.style, { left: box.x + "px", top: box.y + "px", width: box.w + "px", height: box.h + "px" });
      const area = el.querySelector(".dg"), svg = el.querySelector("svg"), n = items.length;
      const aw = area.clientWidth, ah = area.clientHeight;
      // centres des cases
      const pos = [], edges = [];
      if (kind === "hub") {
        pos.push([aw / 2, ah / 2]);
        for (let i = 1; i < n; i++) { const a = -Math.PI / 2 + ((i - 1) / (n - 1)) * Math.PI * 2 + (n === 3 ? Math.PI / 2 : 0);
          pos.push([aw / 2 + Math.cos(a) * aw * 0.33, ah / 2 + Math.sin(a) * ah * 0.33]); edges.push([0, i]); }
      } else if (kind === "cycle") {
        for (let i = 0; i < n; i++) { const a = -Math.PI / 2 + (i / n) * Math.PI * 2; pos.push([aw / 2 + Math.cos(a) * aw * 0.3, ah / 2 + Math.sin(a) * ah * 0.32]); }
        for (let i = 0; i < n; i++) edges.push([i, (i + 1) % n]);
      } else if (kind === "tree") {
        pos.push([aw / 2, ah * 0.22]);
        for (let i = 1; i < n; i++) { pos.push([(aw * (i - 0.5)) / (n - 1), ah * 0.76]); edges.push([0, i]); }
      } else {
        const row = n <= 3 ? n : Math.ceil(n / 2);
        for (let i = 0; i < n; i++) {
          const r = Math.floor(i / row), c = r % 2 ? row - 1 - (i % row) : i % row;
          pos.push([(aw * (c + 0.5)) / row, n <= 3 ? ah / 2 : ah * (0.26 + r * 0.48)]);
          if (i) edges.push([i - 1, i]);
        }
      }
      const cols = kind === "flow" ? (n <= 3 ? n : Math.ceil(n / 2)) : kind === "tree" ? Math.max(2, n - 1) : 3;
      // cases aussi grandes que le plateau le permet (largeur par colonne ET hauteur par rangée)
      const rows = kind === "flow" ? (n <= 3 ? 1 : 2) : kind === "tree" ? 2 : 3;
      const nw = Math.min((aw / cols) * 0.86, P.W * 0.36), fs = Math.min(42 * U, nw / 5.4, (ah / rows) / 4.2);
      const vertical = kind !== "tree";
      const nodes = items.map((it, i) => {
        const d = document.createElement("div"), [c, bg] = tone(i), center = kind === "hub" && i === 0;
        d.className = "dnode" + (vertical ? " v" : "") + (center ? " center" : "");
        const ic = it.icon || EMO2ICON[it.emoji]; // icône au trait dans une pastille teintée (pas d'emoji : ça fait « généré »)
        d.innerHTML = (ic ? `<b style="background:${bg}">${icon(ic, c)}</b>` : "") + `<span${it.tone ? ` style="color:${c}"` : ""}>${rich(it.text)}</span>`;
        Object.assign(d.style, { left: pos[i][0] + "px", top: pos[i][1] + "px", width: (center ? nw * 0.9 : nw) + "px", fontSize: fs + "px" });
        area.appendChild(d);
        gsap.set(d, { xPercent: -50, yPercent: -50 });
        return d;
      });
      const half = nodes.map((d) => [d.offsetWidth / 2 + 6 * U, d.offsetHeight / 2 + 6 * U]);
      const edgePt = (i, dx, dy) => { const [hw, hh] = half[i], k = Math.min(hw / (Math.abs(dx) || 1e-6), hh / (Math.abs(dy) || 1e-6)); return [pos[i][0] + dx * k, pos[i][1] + dy * k]; };
      svg.setAttribute("viewBox", `0 0 ${aw} ${ah}`);
      Object.assign(svg.style, { width: aw + "px", height: ah + "px" });
      let halo = null;
      if (kind === "hub") { // halo autour du centre
        halo = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        Object.entries({ cx: pos[0][0], cy: pos[0][1], r: Math.max(...half[0]) * 1.35, class: "halo" }).forEach(([k, v]) => halo.setAttribute(k, v));
        svg.appendChild(halo);
      }
      const links = edges.map(([a, b]) => {
        const dx = pos[b][0] - pos[a][0], dy = pos[b][1] - pos[a][1];
        let [sx, sy] = edgePt(a, dx, dy), [ex, ey] = edgePt(b, -dx, -dy), d;
        if (kind === "tree") { [sx, sy] = [pos[a][0] + (dx > 0 ? 1 : dx < 0 ? -1 : 0) * half[a][0] * 0.4, pos[a][1] + half[a][1]]; [ex, ey] = [pos[b][0], pos[b][1] - half[b][1]];
          d = `M${sx} ${sy}C${sx} ${(sy + ey) / 2} ${ex} ${sy + (ey - sy) * 0.35} ${ex} ${ey}`; }
        else if (kind === "cycle") { const mx = (sx + ex) / 2 - (ey - sy) * 0.22, my = (sy + ey) / 2 + (ex - sx) * 0.22; d = `M${sx} ${sy}Q${mx} ${my} ${ex} ${ey}`; }
        else if (kind === "flow") { const mx = (sx + ex) / 2; d = `M${sx} ${sy}C${mx} ${sy} ${mx} ${ey} ${ex} ${ey}`; }
        else d = `M${sx} ${sy}L${ex} ${ey}`;
        const [c] = tone(b), g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        g.innerHTML = `<path class="ln${kind === "hub" ? " dash" : ""}" d="${d}" stroke="${c}"/>` +
          `<circle class="end" cx="${ex}" cy="${ey}" r="${5 * U}" fill="${c}"/><circle class="dot" r="${6 * U}" fill="${c}"/>`;
        svg.appendChild(g);
        return g;
      });
      show(el, e.t);
      tl.fromTo(el, { autoAlpha: 0, y: -16 * U, scale: 0.97 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.35, ease: "power3.out" }, e.t);
      if (halo) { gsap.set(halo, { transformOrigin: "50% 50%" });
        tl.fromTo(halo, { autoAlpha: 0, scale: 0.6 }, { autoAlpha: 1, scale: 1, duration: 0.5, ease: "power3.out" }, items[0].t);
        tl.to(halo, { scale: 1.08, duration: 0.8, yoyo: true, repeat: Math.max(1, Math.floor((e.dur - 1) / 0.8)), ease: "sine.inOut" }, items[0].t + 0.5); }
      nodes.forEach((d, i) => {
        const t = items[i].t;
        tl.fromTo(d, { autoAlpha: 0, scale: 0.7, y: 10 * U }, { autoAlpha: 1, scale: 1, y: 0, duration: 0.4, ease: "back.out(1.8)" }, t);
        if (d.querySelector(".ico")) draw(d, t + 0.08, 0.4); // l'icône se dessine au trait
        markers(d, t + 0.3);
      });
      // liens : se tracent vers la case qu'ils rejoignent, juste avant qu'elle apparaisse ; la boucle se referme à la fin
      const tLast = Math.max(...items.map((x) => x.t));
      links.forEach((g, k) => {
        const [a, b] = edges[k], t = kind === "cycle" && b === 0 ? tLast + 0.35 : items[b].t - 0.18, ln = g.querySelector(".ln");
        const L = ln.getTotalLength();
        if (kind === "hub") tl.fromTo(ln, { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.3 }, t);
        else { gsap.set(ln, { strokeDasharray: L, strokeDashoffset: L }); tl.to(ln, { strokeDashoffset: 0, duration: 0.3, ease: "power2.out" }, t); }
        tl.fromTo(g.querySelector(".end"), { scale: 0, transformOrigin: "50% 50%" }, { scale: 1, duration: 0.2, ease: "back.out(3)" }, t + 0.25);
        // point qui voyage le long du lien, en boucle, décalé d'un lien à l'autre
        const dot = g.querySelector(".dot"), o = { v: 0 }, start = Math.max(t + 0.4, tLast + 0.5) + k * 0.18;
        const place = () => { const q = ln.getPointAtLength(o.v * L); dot.setAttribute("cx", q.x); dot.setAttribute("cy", q.y); };
        gsap.set(dot, { autoAlpha: 0 });
        const rep = Math.floor((e.t + e.dur - 0.5 - start) / 0.9);
        if (rep >= 1) { tl.set(dot, { autoAlpha: 1 }, start);
          tl.fromTo(o, { v: 0 }, { v: 1, duration: 0.9, ease: "none", repeat: rep - 1, onUpdate: place }, start);
          tl.set(dot, { autoAlpha: 0 }, start + rep * 0.9); }
      });
      tl.to(el, { autoAlpha: 0, y: -16 * U, duration: 0.3, ease: "power2.in" }, e.t + e.dur - 0.3);
    },

    // maquette de site qui évolue au fil de la parole : HTML brut au départ, puis chaque étape (steps[].do) la transforme.
    // do : color (couleurs, le titre change de teinte) · font (police, titre plus grand) · flex (blocs en ligne) · grid (grille 2x2)
    // · mobile / desktop (la fenêtre passe au format téléphone et la page se réorganise) · menu (le menu s'ouvre)
    // · form (formulaire rempli puis envoyé) · click (clic sur le bouton : retour visuel) · anim (les blocs s'animent)
    // start : actions déjà appliquées à l'apparition (ex ["color", "font", "flex"] pour partir d'un site fini)
    site(e) {
      const p = e.params, box = { x: P.W * 0.05, y: panelTop, w: P.W * 0.9, h: vTopAt(e.t) - panelTop - P.H * 0.02 };
      // étiquettes d'étape dans la barre (label de départ, puis steps[].label) : une seule visible à la fois
      const labels = [p.label || "", ...(p.steps || []).filter((x) => x.label).map((x) => x.label)];
      const el = make("site", `<div class="sc-bar"><b></b><b></b><b></b><span>${esc(p.title || "mon-site.fr")}</span>`
        + labels.map((x) => `<em class="s-lab"${x ? "" : ' style="display:none"'}>${esc(x)}</em>`).join("") + `</div><div class="pg"></div>`, 30 * U);
      const labEls = [...el.querySelectorAll(".s-lab")], url = el.querySelector(".sc-bar span");
      labEls.forEach((x, i) => i && gsap.set(x, { display: "none" }));
      let labK = 0;
      (p.steps || []).forEach((x) => {
        if (!x.label) return;
        tl.set(labEls[labK], { display: "none" }, x.t);
        labK += 1;
        tl.set(labEls[labK], { display: "inline-block" }, x.t);
        tl.fromTo(labEls[labK], { scale: 0.6, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: 0.3, ease: "back.out(2.5)", immediateRender: false }, x.t);
      });
      Object.assign(el.style, { left: box.x + "px", top: box.y + "px", width: box.w + "px", height: box.h + "px" });
      const pg = el.querySelector(".pg"), barH = el.querySelector(".sc-bar").offsetHeight;
      pg.style.top = barH + "px";
      const PH = box.h - barH, F = PH / 10.5, mw = Math.min(box.w * 0.62, PH * 0.75);
      const C = { ink: "#1d1d2b", brand: "#5b4cdb", head: "#1f1f2e", cards: ["#ff9f9f", "#8fcbff", "#8be0a4", "#ffd36b"] };
      const add = (cls, html = "") => { const d = document.createElement("div"); d.className = cls; d.innerHTML = html; pg.appendChild(d); return d; };
      const E = {
        head: add("s-head"), logo: add("s-logo"),
        nav: add("s-nav", "<u>Accueil</u><u>Projets</u><u>Contact</u>"), burger: add("s-burger", "<i></i><i></i><i></i>"),
        title: add("s-title", esc(p.heading || "Mon site")), l1: add("s-line"), l2: add("s-line"), btn: add("s-btn", esc(p.button || "Contact")),
        cards: [0, 1, 2, 3].map(() => add("s-card")),
      };
      const drawer = add("s-drawer", ["Accueil", "Projets", "Contact"].map((x) => `<div>${x}</div>`).join(""));
      const form = add("s-form", `<h5>Contact</h5><div class="in"><span></span></div><div class="in"><span></span></div><div class="go"><span>Envoyer</span><span class="ok">✓ Envoyé</span></div>`);
      const toast = add("s-toast", "Merci ! 🎉");
      const cursor = add("s-cursor", `<svg viewBox="0 0 24 24"><path d="M4 2l6.5 19 2.6-7.6L21 11z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>`);
      const ripple = add("s-ripple");
      E.nav.style.fontSize = 0.55 * F + "px";
      const navW = E.nav.offsetWidth; // mesurée en police par défaut ; Montserrat est ~25 % plus large
      const st = { color: false, font: false, cards: "stack", mobile: false, menu: false, form: false };
      // positions de chaque bloc pour un état donné (px, relatifs à la page)
      const L = (s) => {
        const pw = s.mobile ? mw : box.w, pad = pw * 0.06, hh = 1.55 * F, o = {};
        o.win = s.mobile ? { left: box.x + (box.w - mw) / 2, width: mw, borderRadius: 1.1 * F } : { left: box.x, width: box.w, borderRadius: 0.8 * 30 * U };
        o.head = { left: 0, top: 0, width: pw, height: hh };
        o.logo = { left: pad, top: hh * 0.3, width: hh * 0.4, height: hh * 0.4 };
        o.nav = { left: pw - pad - navW * (s.font ? 1.3 : 1.05), top: hh * 0.3, fontSize: 0.55 * F, autoAlpha: s.mobile || s.menu ? 0 : 1 };
        o.burger = { left: pw - pad - 1.1 * F, top: hh / 2 - 0.42 * F, width: 1.1 * F, height: 0.84 * F, autoAlpha: s.mobile || s.menu ? 1 : 0 };
        const tw = (pw - 2 * pad) / (String(p.heading || "Mon site").length * 0.66);
        const ts = Math.min(s.font ? 1.8 * F : 1.3 * F, tw);
        o.title = { left: pad, top: hh + 0.45 * F, fontSize: ts };
        let y = hh + 0.45 * F + ts * 1.25 + 0.2 * F;
        o.l1 = { left: pad, top: y, width: (pw - 2 * pad) * 0.82, height: 0.36 * F }; y += 0.6 * F;
        o.l2 = { left: pad, top: y, width: (pw - 2 * pad) * 0.55, height: 0.36 * F }; y += 0.75 * F;
        o.btn = { left: pad, top: y, width: 4.2 * F, height: 1.25 * F, fontSize: 0.58 * F }; y += 1.25 * F + 0.55 * F;
        const g = 0.4 * F, avail = Math.max(1.5 * F, PH - 0.5 * F - y), cw = pw - 2 * pad;
        o.cards = [0, 1, 2, 3].map((i) => {
          if (s.cards === "grid" && !s.mobile) return { left: pad + (i % 2) * ((cw + g) / 2), top: y + Math.floor(i / 2) * ((avail + g) / 2), width: (cw - g) / 2, height: (avail - g) / 2, autoAlpha: 1 };
          const k = Math.min(i, 2);
          if (s.cards === "row" && !s.mobile) return { left: pad + k * ((cw + g) / 3), top: y, width: (cw - 2 * g) / 3, height: avail, autoAlpha: i < 3 ? 1 : 0 };
          return { left: pad, top: y + k * ((avail + g) / 3), width: cw, height: (avail - 2 * g) / 3, autoAlpha: i < 3 ? 1 : 0 };
        });
        o.drawer = { left: s.menu ? pw * 0.38 : pw, top: hh, width: pw * 0.62, height: PH - hh };
        o.form = { left: pad, top: hh + 0.6 * F, width: pw - 2 * pad, height: PH - hh - 1.2 * F };
        return o;
      };
      const layout = (t, d) => {
        const o = L(st), to = (x, v) => (d ? tl.to(x, { ...v, duration: d, ease: "power3.inOut" }, t) : tl.set(x, v, t));
        to(el, o.win);
        to(url, { autoAlpha: st.mobile ? 0 : 1, width: st.mobile ? 0 : "auto" });
        for (const k of ["head", "logo", "nav", "burger", "title", "l1", "l2", "btn", "drawer", "form"]) to(k === "drawer" ? drawer : k === "form" ? form : E[k], o[k]);
        E.cards.forEach((c, i) => to(c, o.cards[i]));
      };
      // curseur : glisse vers un bloc puis clique (onde)
      let cur = { x: box.w * 0.8, y: PH * 0.9 }, menuAt = -9;
      const click = (target, t, move = 0.35) => {
        const r = target();
        tl.to(cursor, { left: r.x, top: r.y, autoAlpha: 1, duration: move, ease: "power2.inOut" }, t);
        tl.to(cursor, { scale: 0.82, duration: 0.08, yoyo: true, repeat: 1 }, t + move);
        tl.fromTo(ripple, { left: r.x - F, top: r.y - F, width: 2 * F, height: 2 * F, scale: 0.2, autoAlpha: 0.7 },
          { scale: 1.3, autoAlpha: 0, duration: 0.45, ease: "power2.out", immediateRender: false }, t + move + 0.03);
        cur = r;
        return t + move + 0.1;
      };
      const at = (k, fx = 0.5, fy = 0.55) => () => { const o = L(st)[k]; return { x: o.left + (o.width || 2 * F) * fx, y: o.top + (o.height || F) * fy }; };
      const ACT = {
        color(t, d) {
          st.color = true;
          tl.to(E.head, { backgroundColor: C.head, borderColor: C.head, duration: d }, t);
          tl.to(E.logo, { backgroundColor: S.accent, duration: d }, t);
          tl.to(E.nav, { color: "#fff", duration: d }, t);
          tl.to([...E.burger.children], { backgroundColor: "#fff", duration: d }, t);
          tl.to([E.l1, E.l2], { backgroundColor: "#c9c9d6", opacity: 1, duration: d }, t);
          tl.to(E.btn, { backgroundColor: C.brand, color: "#fff", borderColor: C.brand, borderRadius: 0.4 * F, duration: d }, t);
          E.cards.forEach((c, i) => tl.to(c, { backgroundColor: C.cards[i], borderColor: "rgba(0,0,0,0)", borderRadius: 0.5 * F, boxShadow: "0 0.15em 0.5em rgba(0,0,0,.12)", duration: d }, t + i * 0.06));
          if (!d) { tl.set(E.title, { color: C.brand }, t); return; }
          // le titre change de couleur sous nos yeux avant de prendre celle du site
          ["#e5383b", "#ff9f1c", "#2b7fff", C.brand].forEach((c, i) => tl.to(E.title, { color: c, duration: 0.18 }, t + i * 0.2));
        },
        font(t, d) {
          st.font = true;
          tl.set([E.title, E.nav, E.btn], { fontFamily: "Montserrat, sans-serif", fontWeight: 900 }, t);
          tl.set(E.nav, { textDecoration: "none" }, t);
          layout(t, d);
        },
        flex(t, d) { st.cards = "row"; layout(t, d); },
        grid(t, d) { st.cards = "grid"; layout(t, d); },
        mobile(t, d) { st.mobile = true; layout(t, d); },
        desktop(t, d) { st.mobile = false; layout(t, d); },
        menu(t, d) {
          if (!d) { st.menu = true; layout(t, 0); return; }
          if (!st.mobile) { st.menu = true; layout(t, 0.25); st.menu = false; } // le burger remplace les liens
          const t1 = click(at("burger"), t - 0.15, 0.2); // le curseur part juste avant le mot : le menu s'ouvre dessus
          st.menu = true; layout(t1, 0.3); menuAt = t1;
          tl.fromTo([...drawer.children], { autoAlpha: 0, x: 12 * U }, { autoAlpha: 1, x: 0, duration: 0.2, stagger: 0.06, immediateRender: false }, t1 + 0.15);
        },
        form(t, d) {
          if (d) t = Math.max(t, menuAt + 0.9); // le menu ouvert reste visible un instant
          if (st.menu) { st.menu = false; layout(t, 0.25); }
          st.form = true;
          const page = [E.title, E.l1, E.l2, E.btn, ...E.cards];
          tl.to(page, { autoAlpha: 0, duration: 0.2 }, t);
          tl.fromTo(form, { autoAlpha: 0, y: 14 * U }, { autoAlpha: 1, y: 0, duration: 0.3, ease: "power3.out", immediateRender: false }, t + 0.1);
          const [a, b] = form.querySelectorAll(".in span"), go = form.querySelector(".go");
          const typeIn = (node, text, t0, dd) => { const o = { n: 0 }; tl.to(o, { n: text.length, duration: dd, ease: "none", onUpdate: () => { node.textContent = text.slice(0, Math.round(o.n)); } }, t0); };
          if (!d) { a.textContent = "Léa"; b.textContent = "lea@mail.fr"; return; }
          typeIn(a, "Léa", t + 0.45, 0.3); typeIn(b, "lea@mail.fr", t + 0.8, 0.45);
          const t1 = click(() => { const o = L(st).form; return { x: o.left + o.width * 0.5, y: o.top + o.height * 0.86 }; }, t + 1.1);
          tl.set(go, { backgroundColor: "#22c55e" }, t1);
          tl.set(go.children[0], { display: "none" }, t1); tl.set(go.children[1], { display: "inline" }, t1);
          tl.fromTo(go, { scale: 1 }, { scale: 1.08, duration: 0.15, yoyo: true, repeat: 1, immediateRender: false }, t1);
        },
        click(t) {
          const target = st.form ? () => { const o = L(st).form; return { x: o.left + o.width * 0.5, y: o.top + o.height * 0.86 }; } : at("btn");
          const t1 = click(target, t);
          if (!st.form) tl.fromTo(E.btn, { scale: 1 }, { scale: 0.92, duration: 0.08, yoyo: true, repeat: 1, immediateRender: false }, t1 - 0.1);
          const o = L(st);
          tl.fromTo(toast, { left: o.head.width / 2, top: PH - 2.2 * F, xPercent: -50, autoAlpha: 0, y: 20 * U },
            { autoAlpha: 1, y: 0, duration: 0.3, ease: "back.out(2)", immediateRender: false }, t1);
          tl.to(toast, { autoAlpha: 0, duration: 0.2 }, t1 + 1.2);
        },
        anim(t) {
          E.cards.forEach((c, i) => tl.fromTo(c, { y: 0, rotation: 0 }, { y: -0.6 * F, rotation: i % 2 ? 3 : -3, duration: 0.18, yoyo: true, repeat: 1, ease: "power2.out", immediateRender: false }, t + i * 0.1));
        },
      };
      // état initial : HTML brut, puis les actions de départ appliquées d'un coup
      layout(e.t, 0);
      tl.set(cursor, { autoAlpha: 0, left: cur.x, top: cur.y }, e.t);
      for (const a of p.start || []) ACT[a] && ACT[a](e.t, 0);
      show(el, e.t);
      tl.fromTo(el, { autoAlpha: 0, y: -30 * U, scale: 0.94 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.4, ease: "power3.out" }, e.t);
      const steps = p.steps || [];
      steps.forEach((s, i) => {
        const gap = (steps[i + 1] ? steps[i + 1].t : e.t + e.dur) - s.t;
        if (ACT[s.do]) ACT[s.do](s.t, Math.max(0.3, Math.min(0.7, gap - 0.15)));
      });
      tl.to(el, { autoAlpha: 0, y: -20 * U, duration: 0.3, ease: "power2.in" }, e.t + e.dur - 0.3);
    },

    // compte à rebours : surgit en grand quand il est annoncé, file dans le coin et y défile jusqu'à la fin
    timer(e) {
      const from = Number(e.params.from || 60), t = e.t, dur = e.dur, RING = 2 * Math.PI * 16;
      const fmt = (s) => { s = Math.max(0, Math.ceil(s - 1e-6)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
      const el = make("timer bx", `<svg class="ring" viewBox="0 0 40 40"><circle class="bg" cx="20" cy="20" r="16"/>`
        + `<circle class="fg" cx="20" cy="20" r="16" style="stroke:${S.accent};stroke-dasharray:${RING} ${RING}"/></svg><b>${fmt(from)}</b>`, TIMER_FONT);
      Object.assign(el.style, { left: P.W * 0.05 + "px", top: P.H * (P.safe.top + 0.012) + "px" });
      const txt = el.querySelector("b"), ring = el.querySelector(".fg");
      // départ : en grand, sous le texte d'accroche à l'ouverture, sinon au centre de la zone haute
      const w = el.offsetWidth, h = el.offsetHeight, k = 2.3;
      const cy = t < 3 ? P.zones.top.y + P.H * 0.2 + h * k / 2 : P.zones.top.y + P.zones.top.h / 2;
      const dx = P.W / 2 - (P.W * 0.05 + w / 2), dy = cy - (P.H * (P.safe.top + 0.012) + h / 2);
      show(el, t);
      tl.fromTo(el, { autoAlpha: 0, x: dx, y: dy, scale: k * 0.7 }, { autoAlpha: 1, scale: k, duration: 0.35, ease: "back.out(2)" }, t);
      tl.to(el, { x: 0, y: 0, scale: 1, duration: 0.6, ease: "power3.inOut" }, t + 1.3);
      const run = Math.min(dur, from), o = { v: from };
      tl.to(o, { v: from - run, duration: run, ease: "none", onUpdate: () => { txt.textContent = fmt(o.v); } }, t);
      // arc restant : longueur réelle du cercle (pathLength n'est pas fiable avec un tween de stroke-dashoffset)
      tl.fromTo(ring, { attr: { "stroke-dashoffset": 0 } }, { attr: { "stroke-dashoffset": RING * run / from }, duration: run, ease: "none" }, t);
      // 10 dernières secondes : rouge, une pulsation par seconde
      for (let s = 10; s >= 1; s--) {
        const at = t + from - s;
        if (at < t + 2 || at > t + dur - 0.3) continue;
        if (s === 10) { tl.set(txt, { color: "#e5383b" }, at); tl.set(ring, { stroke: "#e5383b" }, at); }
        tl.fromTo(el, { scale: 1.12 }, { scale: 1, duration: 0.3, ease: "power2.out", immediateRender: false }, at);
      }
      if (dur > from + 0.3) tl.to(el, { x: 8 * U, duration: 0.05, yoyo: true, repeat: 5 }, t + from); // temps écoulé
      leave(el, t + dur);
    },

    flash(e) {
      const el = make("flash", "");
      show(el, e.t);
      tl.fromTo(el, { autoAlpha: 0 }, { autoAlpha: 0.85, duration: e.dur * 0.3, ease: "power1.out" }, e.t);
      tl.to(el, { autoAlpha: 0, duration: e.dur * 0.7, ease: "power1.in" }, e.t + e.dur * 0.3);
    },
  };

  // ✓ / ✗ : bloc propre avec emoji 3D (ou celui donné) + texte révélé
  function pill(e, name, shake) {
    const el = make("mark bx", emo(e.params.logo || e.params.emoji || name) + masked(rich(e.params.text)), 76 * U);
    placeTop(el); fit(el, P.W * 0.88);
    enter(el, e.t);
    reveal(el, e.t + 0.1, 0.4);
    markers(el, e.t + 0.4);
    if (shake) tl.to(el, { x: 10 * U, duration: 0.05, yoyo: true, repeat: 5 }, e.t + 0.4);
    leave(el, e.t + e.dur);
    if (e.params.burst) burst(...topCenter(), e.t, 1.1);
  }



  // sous-titres mot par mot ; pendant une liste, le visage descend : ils passent en bas de l'écran
  const cb = P.zones.cap;
  const inList = (g) => P.layout.low.some(([a, b]) => g.end > a + 0.15 && g.start < b);
  for (const g of P.captions) {
    const el = make("cap", g.words.map((w) => `<span><em style="background:${S.accent}"></em>${esc(w.w)}</span>`).join(""), S.capSize * U);
    const y = inList(g) ? P.H * (P.safe.bottom - 0.01) - cb.h : cb.y; // jamais sous le nom / la description de l'appli
    Object.assign(el.style, { left: cb.x + "px", top: y + "px", width: cb.w + "px", height: cb.h + "px" });
    // un mot trop long (surtout mis en valeur) ne doit pas sortir de la zone
    const widest = Math.max(...[...el.querySelectorAll("span")].map((sp, i) => sp.offsetWidth * (g.words[i].hl ? 1.2 : 1.05)));
    if (widest > cb.w) el.style.fontSize = S.capSize * U * (cb.w / widest) + "px";
    show(el, g.start);
    tl.fromTo(el, { autoAlpha: 0, scale: 0.8, y: 12 * U },
      { autoAlpha: 1, scale: 1, y: 0, duration: 0.13, ease: "back.out(3)" }, g.start);
    tl.set(el, { autoAlpha: 0 }, g.end);
    el.querySelectorAll("span").forEach((sp, i) => {
      const w = g.words[i];
      // mot prononcé : coup de marqueur jaune derrière, texte noir ; mot fort (highlight) : le marqueur reste
      const bar = sp.querySelector("em");
      tl.fromTo(bar, { scaleX: 0 }, { scaleX: 1, duration: 0.09, ease: "power2.out" }, w.s);
      tl.set(sp, { attr: { class: "on" } }, w.s);
      if (w.hl) tl.fromTo(sp, { scale: 1 }, { scale: 1.1, duration: 0.15, ease: "back.out(4)" }, w.s);
      else { // un mot très court (« à ») : on n'efface qu'après la fin du coup de marqueur, sinon il resterait
        const off = Math.max(w.next, w.s + 0.1);
        tl.set(bar, { scaleX: 0 }, off); tl.set(sp, { attr: { class: "" } }, off);
      }
    });
  }

  for (const e of P.events) if (FX[e.fx]) FX[e.fx](e);

  // ombre portée de la vidéo rétrécie (la vidéo elle-même est réduite et arrondie par ffmpeg, même minutage)
  for (const [a, b] of P.layout.windows) {
    const sh = make("vshadow", "");
    const k = P.layout.windows.find((x) => x[0] === a)[2], w = P.W * k, h = P.H * k, full = { left: 0, top: 0, width: P.W, height: P.H, borderRadius: P.layout.radius };
    const small = { left: (P.W - w) / 2, top: P.H - h - P.layout.margin, width: w, height: h, borderRadius: P.layout.radius * k };
    show(sh, a);
    tl.fromTo(sh, { ...full, autoAlpha: 0 }, { ...small, autoAlpha: 1, duration: 0.35, ease: "none" }, a);
    tl.to(sh, { ...full, autoAlpha: 0, duration: 0.35, ease: "none" }, b - 0.35);
  }

  window.__timelines = window.__timelines || {};
  window.__timelines["main"] = tl;
  tl.seek(0);
  }
})();
