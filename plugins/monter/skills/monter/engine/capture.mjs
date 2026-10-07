// capture.mjs - capture une page web en entier (pour l'animer en défilement dans le montage).
// Pilote le Chrome sans interface d'HyperFrames par le protocole DevTools (WebSocket natif de Node 22+),
// sans dépendance npm.
//
// Usage : node capture.mjs <url> <sortie.jpg> [--mobile] [--focus "texte"] [--screens 3]
// --focus : la capture commence à l'élément qui contient ce texte (ex. "README", "Offres d'emploi")
// Sortie : l'image + <sortie>.json {title, url, width, height}. Code 2 = page bloquée (anti-robot, erreur).
import { spawn } from "node:child_process";
import { existsSync, readdirSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

const args = process.argv.slice(2);
const url = args[0], out = args[1];
const opt = (k, d) => { const i = args.indexOf(k); return i < 0 ? d : args[i + 1]; };
const mobile = args.includes("--mobile");
const focus = opt("--focus", "");
const screens = parseFloat(opt("--screens", "3"));
if (!url || !out) { console.error("usage : node capture.mjs <url> <sortie.jpg> [--mobile] [--focus texte]"); process.exit(1); }

const VIEW = mobile ? { width: 412, height: 860, deviceScaleFactor: 2.6, mobile: true }
                    : { width: 1280, height: 820, deviceScaleFactor: 1.5, mobile: false };
const UA = mobile
  ? "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
  : "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36";

function findChrome() {
  if (process.env.CHROME_PATH && existsSync(process.env.CHROME_PATH)) return process.env.CHROME_PATH;
  const base = join(homedir(), ".cache", "hyperframes", "chrome");
  const walk = (d, depth) => {
    if (depth > 5 || !existsSync(d)) return null;
    for (const f of readdirSync(d, { withFileTypes: true })) {
      const p = join(d, f.name);
      if (f.isFile() && /^chrome-headless-shell(\.exe)?$/.test(f.name)) return p;
      if (f.isDirectory()) { const r = walk(p, depth + 1); if (r) return r; }
    }
    return null;
  };
  return walk(base, 0) || [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "/usr/bin/google-chrome", "/usr/bin/chromium",
  ].find(existsSync);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chrome = findChrome();
if (!chrome) { console.error("Chrome introuvable (lance un rendu une fois pour qu'HyperFrames le télécharge, ou CHROME_PATH=...)"); process.exit(1); }
const profile = mkdtempSync(join(tmpdir(), "cap-"));
const proc = spawn(chrome, ["--headless", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
  "--hide-scrollbars", "--mute-audio", "--lang=fr-FR", "--no-first-run", "--disable-blink-features=AutomationControlled",
  `--window-size=${VIEW.width},${VIEW.height}`, "about:blank"], { stdio: ["ignore", "ignore", "pipe"] });
// profil temporaire : effacé une fois Chrome vraiment arrêté (il y écrit encore en se fermant)
const quit = async (code) => {
  const gone = new Promise((r) => proc.once("exit", r));
  proc.kill();
  await Promise.race([gone, sleep(3000)]);
  try { rmSync(profile, { recursive: true, force: true, maxRetries: 3 }); } catch {}
  process.exit(code);
};
const fail = (msg, code = 1) => { console.error(msg); quit(code); };
setTimeout(() => fail("capture trop longue (60 s)"), 60000).unref();

const wsUrl = await new Promise((res, rej) => {
  let buf = "";
  proc.stderr.on("data", (d) => { buf += d; const m = buf.match(/ws:\/\/\S+/); if (m) res(m[0]); });
  proc.on("exit", () => rej(new Error("Chrome s'est arrêté au démarrage")));
}).catch((e) => fail(e.message));

const ws = new WebSocket(wsUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let seq = 0;
const pending = new Map(), listeners = [];
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { const p = pending.get(m.id); pending.delete(m.id); m.error ? p.rej(new Error(m.error.message)) : p.res(m.result); }
  else if (m.method) listeners.forEach((l) => l(m));
});
const send = (method, params = {}, sessionId) => new Promise((res, rej) => {
  const id = ++seq; pending.set(id, { res, rej });
  ws.send(JSON.stringify({ id, method, params, ...(sessionId && { sessionId }) }));
});

const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId: s } = await send("Target.attachToTarget", { targetId, flatten: true });
const page = (m, p) => send(m, p, s);
const evaluate = async (expr) => (await page("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result.value;

await page("Page.enable");
await page("Emulation.setDeviceMetricsOverride", VIEW);
await page("Network.setUserAgentOverride", { userAgent: UA, acceptLanguage: "fr-FR,fr;q=0.9,en;q=0.8" });
const loaded = new Promise((r) => listeners.push((m) => m.method === "Page.loadEventFired" && m.sessionId === s && r()));
const nav = await page("Page.navigate", { url });
if (nav.errorText) fail(`page inaccessible : ${nav.errorText}`, 2);
await Promise.race([loaded, sleep(15000)]);
await sleep(1500);

// bandeaux cookies / consentement : on clique « accepter » (fr/en), y compris dans les iframes même origine,
// puis on masque ce qui reste collé à l'écran (bannière, pop-up d'appli) en recouvrant une bonne partie
await evaluate(`(() => {
  const re = /^(tout accepter|accepter|j'accepte|accept|allow all|agree|i agree|got it|ok$|continuer sans accepter|autoriser)/i;
  for (const b of document.querySelectorAll('button, [role=button], a, input[type=button], input[type=submit]')) {
    const t = (b.innerText || b.value || b.getAttribute('aria-label') || '').trim();
    if (t.length < 40 && re.test(t) && b.getClientRects().length) { b.click(); return t; }
  }
})()`);
await sleep(800);
await evaluate(`(() => {
  const vw = innerWidth, vh = innerHeight;
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.position !== 'fixed' && cs.position !== 'sticky') continue;
    const r = el.getBoundingClientRect();
    const cover = (Math.min(r.right, vw) - Math.max(r.left, 0)) * (Math.min(r.bottom, vh) - Math.max(r.top, 0)) / (vw * vh);
    // en-tête collé en haut : gardé ; le reste (bandeau en bas, pop-up) apparaîtrait au milieu de la capture
    if (cover > 0.18 || r.top > vh * 0.12 || /cookie|consent|gdpr|onetrust|didomi|banner|modal|overlay/i.test(el.id + ' ' + el.className)) el.style.setProperty('display', 'none', 'important');
  }
  for (const n of [document.documentElement, document.body]) { n.style.setProperty('overflow', 'visible', 'important'); }
})()`);
await sleep(800);

const title = await evaluate("document.title");
const bodyLen = await evaluate("document.body ? document.body.innerText.length : 0");
if (/just a moment|attention required|access denied|forbidden|captcha|are you a robot|vérification|robot/i.test(title) || bodyLen < 200)
  fail(`page bloquée ou vide (titre « ${title} ») : choisis un autre site`, 2);

// défilement complet pour déclencher le chargement paresseux des images, puis retour
const startY = focus ? await evaluate(`(() => {
  // plus petit élément visible dont le texte contient la recherche (le texte peut être réparti sur plusieurs balises)
  const t = ${JSON.stringify(focus)}.toLowerCase().replace(/\\s+/g, ' ');
  const has = (el) => (el.innerText || '').toLowerCase().replace(/\\s+/g, ' ').includes(t);
  let best = null;
  for (const el of document.querySelectorAll('body *'))
    if (has(el) && ![...el.children].some(has) && el.getClientRects().length) { best = el; break; }
  if (!best) return 0;
  return Math.max(0, Math.round(best.getBoundingClientRect().top + scrollY - 80));
})()`) : 0;
const pageH = await evaluate("Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)");
const capH = Math.max(VIEW.height, Math.min(pageH - startY, Math.round(VIEW.height * screens)));
for (let y = startY; y < startY + capH; y += VIEW.height / 2) { await evaluate(`scrollTo(0, ${y})`); await sleep(250); }
await evaluate("scrollTo(0, 0)");
await sleep(600);

const shot = await page("Page.captureScreenshot", { format: "jpeg", quality: 88, captureBeyondViewport: true,
  clip: { x: 0, y: startY, width: VIEW.width, height: capH, scale: 1 } });
writeFileSync(out, Buffer.from(shot.data, "base64"));
const finalUrl = await evaluate("location.href");
writeFileSync(out + ".json", JSON.stringify({ title, url: finalUrl, width: VIEW.width * VIEW.deviceScaleFactor,
  height: capH * VIEW.deviceScaleFactor, view_height: VIEW.height * VIEW.deviceScaleFactor }));
console.log(`${out}  (${title})`);
await quit(0);
