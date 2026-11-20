// "Results" tab: pick a run, show headline numbers, default figures with how to read them, and tables.

import { $, bus, figureView, fmt, get, h, post, table, toast } from "./util.js";
import { libraryViews } from "./library.js";

const FIGURES = [
  {
    file: "r2.png", short: "Image fit", title: "Does the simulated image match the real one?",
    alt: "Image R² per image and cycle, before and after correction",
    read: "Each dot is one image (one tile in one cycle). R² is the share of pixel-to-pixel brightness variation the simulation explains (1 = all of it).",
    bio: "Simulating from the original Feather RFU counts neighbours' light twice: once in each cluster's own RFU, and again as it spreads. So the simulated image is too bright and R² is low or even negative. After correction each photon belongs to one cluster, and R² should rise and be similar across cycles.",
  },
  {
    file: "feather_vs_corrected.png", short: "Cluster change", title: "Each cluster before and after correction",
    alt: "Density of corrected RFU against Feather RFU for trusted clusters",
    read: "One point per cluster (a sample of trusted clusters). Points below the dashed line lost RFU; the dotted line is zero light.",
    bio: "The lost RFU is light that the original measurement borrowed from neighbouring colonies. Corrected values stay on Feather's scale, so a cluster with no dye of its own lands on the zero-light line, not at 0. Blank subtraction removes that offset as usual.",
  },
  {
    file: "change_vs_distance.png", short: "Crowding", title: "RFU change by crowding",
    alt: "Median RFU change against the distance to the nearest lit neighbour",
    read: "Clusters grouped by the distance to their nearest neighbour that emits light. The line is the median change, the band the middle half.",
    bio: "Bleedover is optical: one colony's light spreads over a few pixels, so it can only inflate neighbours within a few pixels. A correction that removes bleedover (rather than rescaling everything) changes crowded clusters most and isolated ones least.",
  },
  {
    file: "origins.png", short: "Samples", title: "Median RFU per sequencing sample",
    alt: "Median Feather and corrected RFU for each sequencing sample",
    read: "One row per sample; blue is Feather, orange corrected. ‘lit’ / ‘dark’ is from alignment_matrix.json.",
    bio: "Samples with no dye in these cycles are built-in controls: their Feather RFU is neighbours' light plus background, and correction should move them toward zero light. Lit samples should keep their biological ordering (for example more binding sites → more signal).",
  },
];

let experiment = null;
let pendingRun = null;
let jobRunning = false;
let runs = [];

export function initResults() {
  $("run-select").addEventListener("change", () => show($("run-select").value));
  $("build-report").addEventListener("click", async () => {
    try { bus.emit("job-started", await post("/api/report/build", { run: $("run-select").value })); }
    catch (error) { toast(error.message); }
  });
  bus.on("experiment", (info) => { experiment = info; refresh(); });
  bus.on("run-folders-changed", () => refresh());
  bus.on("runs-changed", () => refresh());
  bus.on("job-state", (job) => { jobRunning = job.status === "running"; });
  bus.on("job-finished", (job) => { pendingRun = job.run_dir.split("/").pop(); });
  bus.on("job-started", (job) => {             // follow a new correction of this experiment right away
    if (job.kind === "correct" && job.experiment === experiment?.name) {
      pendingRun = job.run_dir.split("/").pop();
      refresh();
    }
  });
}

async function refresh() {
  const select = pendingRun;
  pendingRun = null;
  const sel = $("run-select");
  if (!experiment?.cycles) { sel.replaceChildren(); return empty("No correction run for this experiment yet."); }
  ({ runs } = await get("/api/runs", { experiment: experiment.name }));
  sel.replaceChildren(...runs.map((r) => h("option", { value: r.run }, runLabel(r))));
  if (!runs.length) return empty("No correction run for this experiment yet. Run one on the left, or, if you ran it with the scripts, add their results/ folder in ⚙ System → Run folders.");
  sel.value = select && runs.some((r) => r.run === select) ? select : runs[0].run;     // newest by default
  show(sel.value);
}

const STATUS = { running: "running", stopped: "stopped early", done: "finished" };

/** Short enough for the menu at any window width; the method goes on the line below the menu. */
function runLabel(r) {
  const when = r.started ? r.started.slice(5, 16) : r.run.slice(0, 13);
  const progress = r.status === "done" ? `${r.images_done} images` : `${STATUS[r.status]} (${r.images_done})`;
  return `${when} · ${progress}`;
}

function describeRun(run) {
  const r = runs.find((x) => x.run === run);
  $("run-method").textContent = r ? `Method: ${r.method} · made by ${r.made_by === "app" ? "this app" : "a script"} · ${r.run}` : "";
}

function empty(text) {
  $("build-report").hidden = true;
  $("run-method").textContent = "";
  $("results").replaceChildren(h("p", { class: "empty" }, text));
  bus.emit("run-selected", null);
  bus.emit("report", null);
}

async function show(run) {
  const entry = runs.find((r) => r.run === run);
  describeRun(run);
  bus.emit("run-selected", entry);
  if (entry && entry.status !== "done") {
    $("build-report").hidden = true;
    bus.emit("report", null);
    const running = entry.status === "running";
    $("results").replaceChildren(
      h("p", { class: "empty" }, running
        ? `This run is in progress: ${entry.images_done} images corrected so far (see the progress bar). The report appears here when it finishes; corrected images can already be checked in the Image viewer.`
        : `This run stopped before finishing, after ${entry.images_done}${entry.images_total ? ` of ${entry.images_total}` : ""} images (method: ${entry.method}). ` +
          (entry.resumable ? "Resume it to fit only the missing images; the finished ones are kept." : "It was made by a script, so resume it with the script.")),
      ...(!running && entry.resumable
        ? [h("p", {}, h("button", { class: "btn btn--filled", type: "button", disabled: jobRunning, onclick: () => resume(entry) }, "Resume this run"))]
        : []));
    return;
  }
  let report;
  try {
    report = await get("/api/report", { run });
  } catch {
    bus.emit("report", null);
    if (jobRunning) {           // the report can't be built while another job runs
      $("build-report").hidden = false;
      $("results").replaceChildren(h("p", { class: "empty" }, "This run has no report yet. It can be built when the current job finishes."));
      return;
    }
    $("build-report").hidden = true;
    $("results").replaceChildren(h("p", { class: "empty" }, "This run has no report yet; building it now (about a minute, see the progress bar)."));
    try { bus.emit("job-started", await post("/api/report/build", { run })); } catch (error) { toast(error.message); }
    return;
  }
  $("build-report").hidden = true;
  render(report);
  bus.emit("report", report);
}

async function resume(entry) {
  try {
    const workers = parseInt($("workers").value, 10) || undefined;
    bus.emit("job-started", await post("/api/run/resume", { run: entry.run, workers }));
  } catch (error) { toast(error.message); }
}

const fileUrl = (report, name) => `/api/report/file?${new URLSearchParams({ run: report.run, name, v: report.created })}`;
let chosenView = null;          // remembered while switching runs

/** The run's metrics as buttons; one graph or table is shown at a time. */
async function render(report) {
  const run = report.run;
  const head = h("div", { class: "section" },
    h("p", { class: "hint" }, `${report.renderer} image model · zero light at ${fmt.int(report.zero_point_rfu)} RFU · report built ${report.created}`),
    h("dl", { class: "stats stats--compact" }, report.headline.map((t) => h("div", { title: t.hint || "" },
      h("dt", {}, t.label), h("dd", {}, t.value)))));
  const correction = [
    ...FIGURES.map((f) => ({ id: f.file, label: f.short, render: () => figureView(fileUrl(report, f.file), f) })),
    ...(report.calibration ? [{ id: "calibration", label: "Calibration", render: () => calibration(report) }] : []),
    { id: "per-cycle", label: "Per cycle", render: () => perCycle(report) },
    ...(report.failed.length ? [{ id: "failed", label: `Not corrected (${report.failed.length})`, render: () => failed(report) }] : []),
  ];
  const library = await libraryViews(run);
  if ($("run-select").value !== run) return;           // another run was picked meanwhile
  // The strip never changes shape: one Library tab (its own views are sub-tabs inside it), then the correction metrics.
  const analysed = !library.some((v) => v.id === "lib-setup");
  const views = [{ id: "library", label: "Library", render: () => libraryPanel(library) }, ...correction];
  if (!views.some((v) => v.id === chosenView)) chosenView = analysed ? "library" : correction[0].id;

  // Browser-style tabs: one strip (role="tablist"), library metrics then correction metrics; arrow keys move along it.
  const area = h("div", { class: "metric-view", id: "metric-view", role: "tabpanel", tabindex: "0" });
  const tab = (v) => h("button", { class: `metric${v.id === "library" ? " metric--library" : ""}`, type: "button", role: "tab",
    id: `tab-${v.id}`, "data-view": v.id, "aria-controls": "metric-view", onclick: () => select(v.id) }, v.label);
  const strip = views.map(tab);
  const buttons = [h("div", { class: "metric-tabs", role: "tablist", "aria-label": "Metrics", onkeydown: moveFocus }, ...strip)];
  const select = (id) => {
    chosenView = id;
    for (const b of document.querySelectorAll(".metric")) {
      const on = b.dataset.view === id;
      b.setAttribute("aria-selected", String(on));
      b.tabIndex = on ? 0 : -1;
    }
    area.setAttribute("aria-labelledby", `tab-${id}`);
    area.replaceChildren(views.find((v) => v.id === id).render());
  };

  $("results").replaceChildren(head, h("div", { class: "metric-panel" }, ...buttons, area),
    h("p", { class: "hint" }, `Files: the run folder ${run}/ (corrected_results.feather has the Feather layout, so utils.rfu works on it; figures are in app_report/).`));
  select(chosenView);
}

function moveFocus(event) {
  const tabs = [...event.currentTarget.querySelectorAll('[role="tab"]')];
  const i = tabs.indexOf(document.activeElement);
  const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[event.key];
  if (i < 0 || next === undefined) return;
  event.preventDefault();
  const target = tabs[(next + tabs.length) % tabs.length];
  target.focus();
  target.click();
}

let chosenSub = "lib-cv";       // the library sub-tab, remembered while switching runs and tabs

/** Library tab: a row of sub-tabs (Normalized SD, Each sequence, …) over one view, or the set-up prompt. */
function libraryPanel(subviews) {
  if (subviews.length === 1) return subviews[0].render();
  if (!subviews.some((v) => v.id === chosenSub)) chosenSub = subviews[0].id;
  const area = h("div", { class: "subtab-view", id: "subtab-view", role: "tabpanel", tabindex: "0" });
  const buttons = subviews.map((v) => h("button", { class: "subtab", type: "button", role: "tab", id: `sub-${v.id}`,
    "data-sub": v.id, "aria-controls": "subtab-view", onclick: () => pick(v.id) }, v.label));
  const pick = (id) => {
    chosenSub = id;
    for (const b of buttons) { const on = b.dataset.sub === id; b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; }
    area.setAttribute("aria-labelledby", `sub-${id}`);
    area.replaceChildren(subviews.find((v) => v.id === id).render());
  };
  const row = h("div", { class: "subtabs", role: "tablist", "aria-label": "Library views", onkeydown: moveFocus }, ...buttons);
  pick(chosenSub);
  return h("div", { class: "library-panel" }, row, area);
}

function perCycle(report) {
  return h("div", { class: "section" },
    h("p", {}, `Medians over the corrected tiles of each cycle. Cluster-level figures sample one tile from each of these cycles: ${report.sampled_cycles.join(", ")}.`),
    h("div", { class: "table-wrap" }, table([
      { key: "cycle", label: "Cycle" }, { key: "images", label: "Images", num: true },
      { key: "r2_start", label: "R² Feather", num: true, format: (v) => fmt.num(v) },
      { key: "r2_corrected", label: "R² corrected", num: true, format: (v) => fmt.num(v) },
      { key: "median_rfu_change", label: "Median RFU change", num: true, format: fmt.signed },
      { key: "zero_light_pct", label: "Zero light", num: true, format: (v) => `${fmt.num(v, 1)}%` },
      { key: "seconds", label: "s / image", num: true, format: fmt.int }], report.tables.per_cycle, { compact: true })));
}

function failed(report) {
  return h("div", { class: "table-wrap" }, table([{ key: "cycle", label: "Cycle" }, { key: "tile", label: "Tile" },
    { key: "status", label: "Reason" }], report.failed, { compact: true }));
}

function calibration(report) {
  const c = report.calibration;
  return h("figure", { class: "figure figure--single", "aria-label": "Calibration for this experiment" },
    h("img", { src: fileUrl(report, "calibration.png"), alt: "Fitted image counts against Feather RFU for isolated dots", width: 800, height: 450 }),
    h("figcaption", {},
      h("p", {}, `${fmt.int(c.single_points)} isolated, lit dots from ${c.cycles.join(", ")} on tiles ${c.tiles.join(", ")} (${c.recipe}${c.lit_roles.length ? `: ${c.lit_roles.join(", ")}` : ""}). ` +
        `Median dot fit R²: ${fmt.num(c.median_r2_shape)} with free brightness, ${fmt.num(c.median_r2_generative)} predicted from RFU.`),
      h("p", {}, h("strong", {}, "Why it's needed. "), "RFU depends on laser power, exposure and MAPA's summing, so it means different amounts of light in different experiments. " +
        "The line converts this experiment's RFU into camera counts, which the image model works in; the dot shape is reused from the base model (same optics).")));
}
