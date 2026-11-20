// "Image viewer" tab: click a tile overview, see real vs simulated (before/after) and residuals for that crop.

import { $, bus, fmt, get, h, toast } from "./util.js";

let run = null;                    // the run chosen in the Results tab
let images = [];
let tileSize = 3200;               // px, from the overview
let center = { x: 1600, y: 1600 };
let requestId = 0;

export function initViewer() {
  bus.on("run-selected", (r) => { run = r; images = []; setup(); });
  $("viewer-cycle").addEventListener("change", () => { fillTiles(); loadTile(); });
  $("viewer-tile").addEventListener("change", loadTile);
  $("viewer-size").addEventListener("change", () => { drawBox(); loadCrop(); });
  $("viewer-map").addEventListener("click", (e) => {
    const rect = $("viewer-overview").getBoundingClientRect();
    center = { x: ((e.clientX - rect.left) / rect.width) * tileSize, y: ((e.clientY - rect.top) / rect.height) * tileSize };
    drawBox(); loadCrop();
  });
  $("viewer-map").addEventListener("keydown", (e) => {
    const step = size() / 2;
    const move = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }[e.key];
    if (!move) return;
    e.preventDefault();
    center = { x: center.x + move[0], y: center.y + move[1] };
    drawBox(); loadCrop();
  });
}

const size = () => Number(document.querySelector('input[name="viewer-size"]:checked').value);

const natural = (a, b) => a.localeCompare(b, undefined, { numeric: true });

async function setup() {
  $("viewer-run").textContent = run
    ? `Showing run ${run.run} (${run.status === "done" ? "finished" : run.status === "running" ? "in progress" : "stopped early"}), chosen in the Results tab. Only images this run corrected are listed.`
    : "";
  if (run) {
    try { ({ images } = await get("/api/run/images", { run: run.run })); } catch { images = []; }
  }
  const has = images.length > 0;
  $("viewer").hidden = !has;
  $("viewer-empty").hidden = has;
  $("viewer-empty").textContent = run ? "This run hasn't corrected any image yet." : "Choose an experiment with a correction run to look at corrected images.";
  if (!has) return;
  const previous = $("viewer-cycle").value;
  const cycles = [...new Set(images.map((i) => i.cycle))].sort(natural);
  $("viewer-cycle").replaceChildren(...cycles.map((c) => h("option", { value: c }, c)));
  $("viewer-cycle").value = cycles.includes(previous) ? previous : cycles[cycles.length - 1];
  fillTiles();
  $("viewer-overview").removeAttribute("src");
}

function fillTiles() {
  const tiles = images.filter((i) => i.cycle === $("viewer-cycle").value).map((i) => i.tile).sort(natural);
  $("viewer-tile").replaceChildren(...tiles.map((t) => h("option", { value: t }, t)));
  $("viewer-tile").value = tiles[Math.floor(tiles.length / 2)];
}

/** Load lazily: only when the tab is opened (the first tile takes a few seconds to read). */
export async function onShow() {
  if (run?.status === "running") await setup();       // pick up images finished since the last look
  if (images.length && !$("viewer-overview").getAttribute("src")) loadTile();
}

async function loadTile() {
  if (!run || !images.length) return;
  const params = { run: run.run, cycle: $("viewer-cycle").value, tile: $("viewer-tile").value };
  $("viewer-stats").replaceChildren(h("div", {}, h("dt", {}, "Loading"), h("dd", {}, "reading the image…")));
  try {
    const out = await get("/api/viewer/overview", params);
    tileSize = out.width;
    $("viewer-overview").src = out.png;
    $("viewer-overview").alt = `Tile ${params.tile}, ${params.cycle}: raw image`;
    drawBox();
    loadCrop();
  } catch (error) { toast(error.message); }
}

function drawBox() {
  const s = size();
  center.x = Math.min(Math.max(center.x, s / 2), tileSize - s / 2);
  center.y = Math.min(Math.max(center.y, s / 2), tileSize - s / 2);
  const box = $("viewer-box");
  Object.assign(box.style, {
    left: `${((center.x - s / 2) / tileSize) * 100}%`, top: `${((center.y - s / 2) / tileSize) * 100}%`,
    width: `${(s / tileSize) * 100}%`, height: `${(s / tileSize) * 100}%`,
  });
  box.hidden = false;
}

async function loadCrop() {
  const s = size();
  const id = ++requestId;
  const img = $("viewer-crop");
  img.setAttribute("aria-busy", "true");
  try {
    const out = await get("/api/viewer/crop", { run: run.run, cycle: $("viewer-cycle").value, tile: $("viewer-tile").value,
      x: Math.round(center.x - s / 2), y: Math.round(center.y - s / 2), size: s });
    if (id !== requestId) return;           // a newer click won
    img.src = out.png;
    img.alt = `Crop x ${out.x0}–${out.x0 + s}, y ${out.y0}–${out.y0 + s}: real, simulated and residual images`;
    const st = out.stats;
    $("viewer-stats").replaceChildren(
      stat("Window", `x ${out.x0}, y ${out.y0}, ${s} px`),
      stat("Clusters here", fmt.int(st.clusters)),
      stat("R² from Feather", fmt.num(st.r2_feather)),
      stat("R² corrected", fmt.num(st.r2_corrected)),
      stat("Median RFU change", `${fmt.signed(st.median_rfu_change)} (of ${fmt.int(st.median_rfu_start)})`));
  } catch (error) {
    toast(error.message);
  } finally {
    if (id === requestId) img.removeAttribute("aria-busy");
  }
}

const stat = (label, value) => h("div", {}, h("dt", {}, label), h("dd", {}, value));
