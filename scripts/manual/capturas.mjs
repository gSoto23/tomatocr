// Screenshots of the user manual (app/static/manual/). See scripts/manual/README.md.
//
//   node scripts/manual/capturas.mjs                 # every shot in capturas.json
//   node scripts/manual/capturas.mjs proyectos       # only shots whose name starts with "proyectos"
//
// Needs the local server with the fictitious data running (MANUAL_BASE_URL, default
// http://127.0.0.1:8124) and Google Chrome. Never point it to production: the manual is
// shown to every role, so a real screenshot would leak other clients' data.
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const BASE = process.env.MANUAL_BASE_URL || "http://127.0.0.1:8124";
const CHROME = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9333;
// MANUAL_OUT_DIR and MANUAL_TOKENS_FILE let it run from a copy outside the project (see README).
const OUT = process.env.MANUAL_OUT_DIR || join(root, "app", "static", "manual");
const VIEWPORTS = {
  desktop: { width: 1280, height: 800, deviceScaleFactor: 1.5, mobile: false },
  mobile: { width: 390, height: 844, deviceScaleFactor: 2, mobile: true },
};

if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) {
  console.error(`MANUAL_BASE_URL debe ser un servidor local, no ${BASE}`);
  process.exit(1);
}

const config = JSON.parse(readFileSync(join(here, "capturas.json"), "utf8"));
const filter = process.argv[2] || "";
const shots = config.shots.filter((s) => s.name.startsWith(filter));
const tokens = JSON.parse(process.env.MANUAL_TOKENS_FILE
  ? readFileSync(process.env.MANUAL_TOKENS_FILE, "utf8")
  : execFileSync(join(root, ".venv", "bin", "python"), [join(here, "tokens.py")],
    { cwd: root, env: { ...process.env, PYTHONPATH: root } }).toString());

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function connect() {
  const base = process.env.MANUAL_CHROME_PROFILE || tmpdir();
  mkdirSync(base, { recursive: true });
  const profile = mkdtempSync(join(base, "manual-chrome-"));
  const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
    "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", "about:blank"], { stdio: "ignore" });
  let list;
  for (let i = 0; i < 150 && !list; i++) {
    await sleep(200);
    list = await fetch(`http://127.0.0.1:${PORT}/json/list`).then((r) => r.json()).catch(() => null);
  }
  const page = list.find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  let id = 0;
  const pending = new Map();
  const listeners = [];
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    } else if (msg.method) {
      listeners.forEach((l) => l(msg));
    }
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const n = ++id;
    pending.set(n, { resolve, reject });
    ws.send(JSON.stringify({ id: n, method, params }));
  });
  const once = (method) => new Promise((resolve) => {
    const l = (msg) => { if (msg.method === method) { listeners.splice(listeners.indexOf(l), 1); resolve(msg); } };
    listeners.push(l);
  });
  await send("Page.enable");
  await send("Runtime.enable");
  return { send, once, close: () => { ws.close(); chrome.kill(); } };
}

// Runs in the page: numbered red markers over the elements named in the shot.
function drawMarkers(markers) {
  const find = (m) => {
    if (m.selector) {
      const visible = [...document.querySelectorAll(m.selector)].filter((el) => el.getBoundingClientRect().width > 0);
      return visible[m.index || 0];
    }
    const tags = m.tags || "a,button,label,h1,h2,h3,th,td,span,div,p,li,summary,option,input,select";
    const wanted = m.text.trim().toLowerCase();
    const matches = [...document.querySelectorAll(tags)].filter((el) => {
      const text = (el.innerText || el.value || el.placeholder || "").trim().toLowerCase();
      return m.exact === false ? text.includes(wanted) : text === wanted;
    }).filter((el) => el.getBoundingClientRect().width > 0);
    if (m.exact === false && m.index === undefined) {
      // The innermost element that holds the text, not a wrapper around half the page.
      const area = (el) => { const r = el.getBoundingClientRect(); return r.width * r.height; };
      return matches.sort((a, b) => area(a) - area(b))[0];
    }
    return matches[m.index || 0];
  };
  const missing = [];
  for (const m of markers) {
    const el = find(m);
    if (!el) { missing.push(m.text || m.selector); continue; }
    const v = el.getBoundingClientRect();
    // Page coordinates, so markers stay put when the capture goes beyond the viewport.
    const r = { left: v.left + scrollX, top: v.top + scrollY, right: v.right + scrollX, width: v.width, height: v.height };
    const pad = m.pad ?? 4;
    const box = document.createElement("div");
    Object.assign(box.style, { position: "absolute", left: `${r.left - pad}px`, top: `${r.top - pad}px`,
      width: `${r.width + 2 * pad}px`, height: `${r.height + 2 * pad}px`, border: "3px solid #dc2626",
      borderRadius: "8px", zIndex: 99998, pointerEvents: "none" });
    const badge = document.createElement("div");
    badge.textContent = m.n;
    const left = m.badge === "right" ? r.right + pad - 11 : r.left - pad - 11;
    Object.assign(badge.style, { position: "absolute", left: `${Math.max(2, left)}px`, top: `${Math.max(2, r.top - pad - 11)}px`,
      width: "22px", height: "22px", borderRadius: "999px", background: "#dc2626", color: "white",
      font: "bold 13px/22px system-ui, sans-serif", textAlign: "center", zIndex: 99999, pointerEvents: "none",
      boxShadow: "0 1px 3px rgba(0,0,0,.4)" });
    document.body.append(box, badge);
  }
  return missing;
}

const cdp = await connect();
let failed = 0;
try {
  for (const shot of shots) {
    const viewport = { ...VIEWPORTS[shot.viewport || "desktop"], ...(shot.height ? { height: shot.height } : {}),
      ...(shot.width ? { width: shot.width } : {}) };
    await cdp.send("Emulation.setDeviceMetricsOverride", viewport);
    await cdp.send("Emulation.setUserAgentOverride", { userAgent: viewport.mobile
      ? "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
      : "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" });
    await cdp.send("Network.clearBrowserCookies").catch(() => {});
    if (shot.as) {
      if (!tokens[shot.as]) throw new Error(`No hay usuario de demostración para '${shot.as}'`);
      await cdp.send("Network.setCookie", { name: "access_token", value: tokens[shot.as], url: BASE });
    }
    const loaded = cdp.once("Page.loadEventFired");
    await cdp.send("Page.navigate", { url: BASE + shot.path });
    await loaded;
    await sleep(shot.wait || 700);
    // Actions before the capture, e.g. open a form: document.querySelector(...).click()
    for (const script of shot.before || []) {
      const { exceptionDetails } = await cdp.send("Runtime.evaluate",
        { expression: `(async () => { ${script} })()`, awaitPromise: true });
      if (exceptionDetails) console.error(`  ${shot.name}: falló un paso previo: ${exceptionDetails.exception?.description || exceptionDetails.text}`);
      await sleep(400);
    }
    // The global loader and toasts never belong in a screenshot.
    await cdp.send("Runtime.evaluate", { expression:
      "document.querySelectorAll('#global-loader,[data-toast]').forEach(e => e.remove())" });
    const { result } = await cdp.send("Runtime.evaluate", {
      expression: `(${drawMarkers})(${JSON.stringify(shot.markers || [])})`, returnByValue: true });
    if (result.value && result.value.length) {
      console.error(`✗ ${shot.name}: no encontré ${JSON.stringify(result.value)}`);
      failed++;
    }
    const params = { format: "webp", quality: 85 };
    if (shot.clip) {
      const { result: rect } = await cdp.send("Runtime.evaluate", { returnByValue: true, expression:
        `(() => { const r = document.querySelector(${JSON.stringify(shot.clip)}).getBoundingClientRect();
          return { x: Math.max(0, r.left + scrollX - 16), y: Math.max(0, r.top + scrollY - 16),
                   width: r.width + 32, height: r.height + 32 }; })()` });
      params.clip = { ...rect.value, scale: 1 };
      params.captureBeyondViewport = true;
    }
    const { data } = await cdp.send("Page.captureScreenshot", params);
    const file = join(OUT, `${shot.name}.webp`);
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, Buffer.from(data, "base64"));
    console.log(`✓ ${shot.name}.webp`);
  }
} finally {
  cdp.close();
}
if (failed) {
  console.error(`${failed} captura(s) con marcas que no encontré; revisá capturas.json.`);
  process.exit(1);
}
