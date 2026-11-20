// Setup cards 2–3: model + optional calibration, correction settings, time estimate, Run.

import { $, bus, chips, debounce, fmt, h, post, table, toast } from "./util.js";

let info = null;
let machine = null;
let jobRunning = false;
let readCalCycles = () => [];
let readCalTiles = () => [];
let readRunCycles = () => [];
let readRunTiles = () => [];

export function initRunConfig(prefs, machineInfo) {
  machine = machineInfo;
  for (const radio of document.querySelectorAll('input[name="renderer"]')) {
    radio.checked = radio.value === (prefs.renderer || "voronoi");
    radio.addEventListener("change", update);
  }
  if (prefs.workers) $("workers").value = prefs.workers;
  $("model").addEventListener("change", onModel);
  $("calibrate").addEventListener("change", update);
  for (const id of ["workers", "prior", "softness", "steps", "cal-max"]) $(id).addEventListener("input", update);
  for (const id of ["run-cycles", "run-tiles", "cal-cycles", "cal-tiles"]) $(id).addEventListener("change", update);
  $("run").addEventListener("click", run);
  bus.on("experiment", (experiment) => {
    info = experiment;
    $("card-model").hidden = $("card-correct").hidden = !info?.cycles;
    if (info?.cycles) load(prefs);
  });
  bus.on("job-state", (job) => {
    const running = job.status === "running";
    if (running !== jobRunning) { jobRunning = running; update(); }
  });
}

function load(prefs) {
  const select = $("model");
  select.replaceChildren(...info.models.map((m) => h("option", { value: m.id, title: m.summary }, m.label)));
  select.value = (info.models.find((m) => m.recommended) || info.models[0]).id;

  const cycles = info.cycles.filter((c) => c.aligned_tiles.length).map((c) => c.cycle);
  const tiles = [...new Set(info.cycles.flatMap((c) => c.aligned_tiles))].sort();
  readRunCycles = chips($("run-cycles"), cycles, cycles);
  readRunTiles = chips($("run-tiles"), tiles, tiles);
  readCalCycles = chips($("cal-cycles"), cycles, info.calibration_defaults.cycles);
  readCalTiles = chips($("cal-tiles"), tiles, info.calibration_defaults.tiles);
  if (!prefs.workers) $("workers").value = info.recommended_workers;
  workersHint(info.memory_per_worker_gb, info.recommended_workers);
  onModel();
}

const selectedModel = () => info?.models.find((m) => m.id === $("model").value);

function onModel() {
  const model = selectedModel();
  const status = $("model-status");
  $("model").title = model?.summary || "";
  if (model?.calibration) {
    const c = model.calibration;
    const source = c.source === "yours" ? `your calibration from ${c.created} (${fmt.int(c.single_points)} dots)` : "built in";
    status.className = "status-line status-line--good";
    status.replaceChildren(h("span", {}, `✓ Calibrated for ${info.name}: counts = ${c.gain.toFixed(2)} × RFU ${c.offset >= 0 ? "+" : "−"} ${fmt.int(Math.abs(c.offset))}`),
      h("span", { class: "hint" }, `${source[0].toUpperCase()}${source.slice(1)} · zero light at ${fmt.int(c.zero_point_rfu)} RFU.`));
  } else {
    status.className = "status-line status-line--warn";
    status.replaceChildren(h("span", {}, `! Not calibrated for ${info.name} yet. Tick below to fit it from isolated dots; it's saved for later runs.`));
  }
  $("calibrate").checked = !!model && !model.calibration;
  update();
}

function settings() {
  return {
    renderer: document.querySelector('input[name="renderer"]:checked')?.value || "voronoi",
    workers: Math.max(1, parseInt($("workers").value, 10) || 1),
    prior: parseFloat($("prior").value), softness: parseFloat($("softness").value), steps: parseInt($("steps").value, 10),
    background_spacing: 64, cycles: readRunCycles(), tiles: readRunTiles(),
  };
}

function imageCount(cycles, tiles) {
  const c = new Set(cycles), t = new Set(tiles);
  return info.cycles.filter((x) => c.has(x.cycle)).reduce((n, x) => n + x.aligned_tiles.filter((tile) => t.has(tile)).length, 0);
}

function update() {
  if (!info?.cycles) return;
  const s = settings();
  const images = imageCount(s.cycles, s.tiles);
  const model = selectedModel();
  const calibrating = $("calibrate").checked;
  $("calibrate-options").hidden = !calibrating;
  const calImages = calibrating ? readCalCycles().length * readCalTiles().length : 0;
  let reason = "";
  if (jobRunning) reason = "A job is running.";
  else if (!info.ready) reason = "This folder isn't ready for correction (see step 1).";
  else if (!model) reason = "Choose a model.";
  else if (!images) reason = "No aligned image selected.";
  else if (!calibrating && !model.calibration) reason = "Tick ‘Calibrate’: this model has no calibration for this experiment.";
  else if (calibrating && !calImages) reason = "Choose at least one calibration cycle and tile.";
  $("run").disabled = Boolean(reason);
  $("run-hint").textContent = reason;
  $("run").textContent = calibrating ? `Calibrate and correct ${images} images` : `Correct ${images} images`;
  if (images) estimate({ ...s, images, calImages });
  else $("estimate").replaceChildren();
}

/** Suggested workers, shown for every experiment (the time estimate also needs aligned images). */
function workersHint(memoryGb, recommended) {
  $("workers-hint").textContent = info.feather?.rows
    ? `~${memoryGb} GB each · ${recommended} recommended on this ${machine.cpus}-core, ${Math.round(machine.memory_gb)} GB computer`
    : `${machine.cpus} cores, ${Math.round(machine.memory_gb)} GB here; a suggestion needs results.feather`;
}

const estimate = debounce(async (s) => {
  try {
    const e = await post("/api/estimate", { renderer: s.renderer, workers: s.workers, images: s.images,
      sources: info.clusters_per_tile, calibration_images: s.calImages });
    const over = s.workers * e.memory_per_worker_gb > 0.8 * machine.memory_gb;
    workersHint(e.memory_per_worker_gb, e.recommended_workers);
    $("estimate").replaceChildren(
      h("div", {}, "Estimated time ", h("strong", {}, `≈ ${fmt.duration(e.seconds)}`)),
      h("div", { class: "hint" }, `${s.images} images · ${s.workers} worker${s.workers > 1 ? "s" : ""} · ~${fmt.int(e.seconds_per_image)} s per image`),
      h("div", { class: "hint" }, `Based on ${e.basis}.`),
      ...(over ? [h("div", { class: "badge badge--warn" }, `! ${s.workers} workers need ~${Math.round(s.workers * e.memory_per_worker_gb)} GB; this computer has ${Math.round(machine.memory_gb)} GB`)] : []));
    $("estimate-table").replaceWith(Object.assign(table(
      [{ key: "workers", label: "Workers", num: true }, { key: "seconds", label: "Time", num: true, format: fmt.duration },
       { key: "memory_gb", label: "Memory", num: true, format: (v) => `${v} GB` },
       { key: "fits", label: "Fits in memory", format: (v) => (v ? "yes" : "no") }],
      e.options, { compact: true, current: (r) => r.workers === s.workers }), { id: "estimate-table" }));
  } catch (error) {
    $("estimate").textContent = error.message;
  }
}, 300);

async function run() {
  const model = selectedModel();
  const s = settings();
  const body = {
    path: info.path, model: model.id,
    calibrate: { enabled: $("calibrate").checked, cycles: readCalCycles(), tiles: readCalTiles(), max_per_image: parseInt($("cal-max").value, 10) },
    correct: s,
    fastq: info.fastq?.found ? { path: info.fastq.path, mode: info.fastq.mode, flowcell_id: info.fastq.flowcell_id || info.details.flowcell_id } : null,
  };
  $("run").disabled = true;
  try {
    const { match } = await post("/api/run/check", body);
    if (match) {
      const choice = await askResume(match);
      if (choice === "cancel") return update();
      if (choice === "resume") body.resume_run = match.run;
    }
    const job = await post("/api/run", body);
    bus.emit("job-started", job);
  } catch (error) {
    toast(error.message);
    update();
  }
}

/** A stopped run with the same method exists: resume it (keeps its images), start a new one, or cancel. */
function askResume(match) {
  const dialog = $("resume-dialog");
  $("resume-text").textContent = `A run of this experiment with the same method stopped before finishing ` +
    `(started ${match.started}, ${match.images_done} images corrected). Resume it to keep those images and ` +
    `fit only the rest, or start a new run from zero.`;
  dialog.returnValue = "cancel";
  dialog.showModal();
  return new Promise((resolve) => dialog.addEventListener("close", () => resolve(dialog.returnValue), { once: true }));
}
