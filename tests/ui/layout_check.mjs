// Layout check: nothing in the app may be cut off or pushed out of view, at any desktop window width.
//
//   node layout_check.mjs <app url> <experiment folder> [width ...]
//
// Drives headless Chrome over the DevTools protocol. At each width it opens the experiment and visits every
// state a user sees (Experiment tab, every Results metric tab, Image viewer, the ⚙ / 🧹 / ? dialogs). In each
// state it reports any visible element that sticks out of the window or out of its card, clips part of its own
// content (overflow hidden/auto with content wider than the box), or a menu whose chosen text doesn't fit.
// Text fields and tables in their scroll boxes are exempt (scrolling is how they show long content).
// Prints a JSON list of problems; exits 1 if there are any.

import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const [url, experiment, ...widthArgs] = process.argv.slice(2);
const widths = widthArgs.length ? widthArgs.map(Number) : [1024, 1100, 1280, 1440, 1920];
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = mkdtempSync(join(tmpdir(), "layout-"));
const chrome = spawn(CHROME, ["--headless=new", "--remote-debugging-port=0", "--hide-scrollbars", "--no-first-run",
  `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
let port = null;
for (let i = 0; i < 100 && !port; i++) {
  const file = join(profile, "DevToolsActivePort");
  if (existsSync(file)) port = readFileSync(file, "utf8").split("\n")[0];
  else await sleep(100);
}
const page = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let nextId = 0;
const waiting = {};
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (waiting[d.id]) { waiting[d.id](d); delete waiting[d.id]; } };
const send = (method, params = {}) => new Promise((r) => { waiting[++nextId] = r; ws.send(JSON.stringify({ id: nextId, method, params })); });
const run = async (expr) => (await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;
const until = async (expr, ms = 30000) => {
  for (const end = Date.now() + ms; Date.now() < end; await sleep(250)) if (await run(expr)) return true;
  return false;
};

// Runs inside the page: every way something can be cut off or pushed out of view.
const CHECK = `(() => {
  const out = [], vw = document.documentElement.clientWidth;
  const name = (el) => el.id ? "#" + el.id : el.tagName.toLowerCase() +
    (typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().split(/\\s+/).join(".") : "");
  const shown = (el) => { const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && !el.closest("[hidden], dialog:not([open])"); };
  if (document.documentElement.scrollWidth > vw + 1)
    out.push("the page is " + document.documentElement.scrollWidth + "px wide in a " + vw + "px window");
  const ctx = document.createElement("canvas").getContext("2d");
  for (const el of document.querySelectorAll("body *")) {
    if (!shown(el) || el.closest(".sr-only")) continue;      // screen-reader-only text is clipped on purpose
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (r.right > vw + 1) out.push(name(el) + " sticks out of the window by " + Math.round(r.right - vw) + "px");
    const box = el.parentElement && el.parentElement.closest(".card, .workspace, .sheet, .expbar, .statusbar, .appbar");
    if (box && r.right > box.getBoundingClientRect().right + 1) out.push(name(el) + " sticks out of " + name(box));
    if (el.matches("input, textarea, pre, .table-wrap, .table-wrap *, svg, svg *")) continue;
    if (cs.overflowX !== "visible" && el.scrollWidth > el.clientWidth + 1)
      out.push(name(el) + " cuts off " + (el.scrollWidth - el.clientWidth) + "px of its content");
    if (el.tagName === "SELECT" && el.selectedOptions[0]) {
      ctx.font = cs.fontWeight + " " + cs.fontSize + " " + cs.fontFamily;
      const text = el.selectedOptions[0].text;
      const room = el.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) - 16;   // 16: the arrow
      if (ctx.measureText(text).width > room + 1) out.push(name(el) + " shows only part of \\"" + text + "\\"");
    }
  }
  const text = document.querySelector(".statusbar__text"), bar = document.querySelector("#status-progress");
  if (text && bar && text.getBoundingClientRect().right > bar.getBoundingClientRect().left + 1)
    out.push(".statusbar__text runs into the progress bar");
  for (const el of document.querySelectorAll(".statusbar *"))
    if (shown(el) && el.getBoundingClientRect().bottom > window.innerHeight + 1) out.push(name(el) + " is cut off below the window");
  return [...new Set(out)];
})()`;

const problems = [];
const check = async (width, state) => {
  for (const p of (await run(CHECK)) || []) problems.push(`${width}px, ${state}: ${p}`);
};

for (const width of widths) {
  await send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: 1, mobile: false });
  await send("Page.navigate", { url });
  await until(`document.readyState === "complete" && !!document.querySelector("#exp-path")`);
  await check(width, "start");
  await run(`(() => { document.querySelector("#status-stage").textContent = "Report built · 261026_103922_correct_20250228_qc_experiment_qc2_slope";
    document.querySelector("#status-detail").textContent = "Report ready in the Results tab."; return 1; })()`);
  await check(width, "status bar with a long run name");
  await run(`(() => { const i = document.querySelector("#exp-path"); i.value = ${JSON.stringify(experiment)};
    i.dispatchEvent(new Event("change")); return 1; })()`);
  if (!(await until(`!document.querySelector("#layout").hidden`, 60000))) { problems.push(`${width}px: experiment didn't load`); continue; }
  await until(`!!document.querySelector("#samples table")`, 30000);
  await check(width, "Experiment tab");

  await run(`document.querySelector("#tab-results").click(), 1`);
  await until(`!!document.querySelector(".metric, #results .empty")`, 60000);
  const tabs = (await run(`[...document.querySelectorAll(".metric")].map((t) => t.dataset.view)`)) || [];
  for (const view of tabs) {
    await run(`document.querySelector('[data-view="${view}"]').click(), 1`);
    await until(`[...document.querySelectorAll("#metric-view img")].every((i) => i.complete)`, 15000);
    await check(width, `Results › ${view}`);
    const subs = (await run(`[...document.querySelectorAll(".subtab")].map((t) => t.dataset.sub)`)) || [];
    for (const sub of subs) {                                   // library views live in sub-tabs
      await run(`document.querySelector('[data-sub="${sub}"]').click(), 1`);
      await until(`[...document.querySelectorAll("#subtab-view img")].every((i) => i.complete) && !document.querySelector("#subtab-view .hint")?.textContent.startsWith("Loading")`, 15000);
      await sleep(400);
      await check(width, `Results › ${view} › ${sub}`);
    }
  }

  await run(`document.querySelector("#tab-viewer").click(), 1`);
  if (await until(`!!document.querySelector("#viewer-crop")?.getAttribute("src")`, 90000)) await check(width, "Image viewer");

  for (const [button, dialog, close] of [["#system", "#system-dialog", "#system-close"], ["#clean", "#clean-dialog", "#clean-close"],
                                         ["#help", "#help-dialog", "#help-close"],
                                         ['[data-opens="model-help"]', "#model-help", "#model-help [data-closes]"],
                                         ['[data-opens="correct-help"]', "#correct-help", "#correct-help [data-closes]"]]) {
    await run(`document.querySelector('${button}').click(), 1`);
    await until(`document.querySelector("${dialog}").open && !document.querySelector("${dialog}").textContent.includes("…") && [...document.querySelectorAll("${dialog} img")].every((i) => i.complete)`, 10000);
    await sleep(800);
    await check(width, `dialog ${dialog}`);
    await run(`document.querySelector('${close}').click(), 1`);
  }
}

console.log(JSON.stringify(problems, null, 1));
ws.close();
chrome.kill();
process.exit(problems.length ? 1 : 0);
