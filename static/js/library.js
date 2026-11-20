// Library analysis: the optional setup card (sample + structure, saved per experiment) and its Results section.

import { $, bus, debounce, figureView, fmt, get, h, post, table, toast } from "./util.js";

let experiment = null;
let jobRunning = false;

export function initLibrary() {
  bus.on("experiment", load);
  bus.on("origins", fillSamples);
  bus.on("job-state", (job) => { jobRunning = job.status === "running"; });
  $("lib-enabled").addEventListener("change", () => { $("lib-options").hidden = !$("lib-enabled").checked; save(); });
  for (const id of ["lib-family", "lib-min"]) $(id).addEventListener("change", save);
  $("lib-template").addEventListener("input", debounce(save, 600));
  $("lib-check").addEventListener("click", check);
}

async function load(info) {
  experiment = info?.cycles && info.feather?.exists ? info : null;
  $("card-library").hidden = !experiment;
  $("lib-status").replaceChildren();
  $("lib-status").className = "status-line";
  if (!experiment) return;
  const { config } = await get("/api/library", { experiment: experiment.name }).catch(() => ({ config: null }));
  if (experiment !== info) return;
  $("lib-enabled").checked = !!config?.enabled;
  $("lib-options").hidden = !config?.enabled;
  $("lib-template").value = config?.template || "";
  $("lib-min").value = config?.min_replicates || 5;
  $("lib-family").dataset.saved = config?.family || "";
}

/** Sample choices come from the Experiment tab's sample table; library samples first. */
function fillSamples(origins) {
  const select = $("lib-family");
  const ordered = [...origins].sort((a, b) => (a.role !== "library") - (b.role !== "library") || b.clusters - a.clusters);
  select.replaceChildren(...ordered.map((o) => h("option", { value: o.family }, `${o.family} · ${o.role_label} · ${fmt.int(o.clusters)} clusters`)));
  const saved = select.dataset.saved;
  if (saved && ordered.some((o) => o.family === saved)) select.value = saved;
}

function config() {
  return { enabled: $("lib-enabled").checked, family: $("lib-family").value, template: $("lib-template").value,
           min_replicates: parseInt($("lib-min").value, 10) || 5 };
}

async function save() {
  if (!experiment) return;
  const status = $("lib-status");
  try {
    await post("/api/library/save", { experiment: experiment.name, config: config() });
    $("lib-family").dataset.saved = $("lib-family").value;
    if (status.classList.contains("status-line--warn")) status.replaceChildren();
    status.className = "status-line";
  } catch (error) {
    status.className = "status-line status-line--warn";
    status.textContent = `! ${error.message}`;
  }
}

async function check() {
  const status = $("lib-status");
  status.className = "status-line status-line--neutral";
  status.textContent = "Matching the structure to this sample's reads…";
  try {
    const r = await post("/api/library/check", { path: experiment.path, family: $("lib-family").value, template: $("lib-template").value });
    const good = r.matched_fraction >= 0.5;
    status.className = `status-line status-line--${good ? "good" : "warn"}`;
    status.replaceChildren(
      h("span", {}, `${good ? "✓" : "!"} ${(100 * r.matched_fraction).toFixed(1)}% of ${fmt.int(r.checked_reads)} reads fit the structure`),
      h("span", { class: "hint" }, `${r.variable_bases} variable bases in ${r.segments} segment${r.segments > 1 ? "s" : ""} · ` +
        `${fmt.int(r.members_seen)}${r.possible_members ? ` of ${fmt.int(r.possible_members)} possible` : ""} members seen · e.g. ${r.examples.slice(0, 3).join(", ")}`),
      good ? "" : h("span", { class: "hint" }, "Few reads fit: check the sample and that the structure starts where the read starts."));
  } catch (error) {
    status.className = "status-line status-line--warn";
    status.textContent = `! ${error.message}`;
  }
}

const FIGURES = [
  { file: "replicates.png", alt: "Histogram and cumulative distribution of replicate clusters per library member",
    read: "Left: how many clusters carry each designed sequence (log-log, as in the replicate notebook). Right: the share of sequences with at most that many. Sequences left of the dashed line have too few replicates to measure their spread and are left out.",
    bio: "Replicates are separate colonies of the same molecule, so they are the flowcell's own repeat measurements of that sequence." },
  { file: "member_medians.png", alt: "Median signal of each library member, corrected against Feather",
    read: "One point per library member: its median signal over its replicates, before (x) and after (y), as light above zero (RFU). Dashed: no change.",
    bio: "If members follow a band parallel to the line, correction removed a similar share of borrowed light everywhere and kept their ranking (see rank agreement below). Members far below the band were the most inflated by neighbours." },
  { file: "member_cv.png", alt: "Distribution of normalized SD of replicates, Feather and corrected",
    read: "Normalized SD = SD of a member's replicates ÷ their mean, so every member is scaled to a mean of 1 and the overall drop in RFU doesn't count.",
    bio: "Replicates should be equally bright. Bleedover makes each replicate's value depend on its random neighbours, which adds spread. A curve shifted left after correction means more reproducible measurements per sequence." },
  { file: "cv_each.png", alt: "Heatmap of each sequence's normalized SD after correction against before",
    read: "One cell per group of sequences: each sequence's normalized SD before (x) and after (y); darker = more sequences. Below the dashed line = that sequence's replicates agree better after correction.",
    bio: "This is what the correction did to each sequence: if bleedover were the main source of replicate disagreement, nearly every sequence would sit below the line. Sequences above it got noisier, which points to something the image model doesn't capture for them." },
  { file: "within.png", alt: "Distribution of each cluster's value divided by its sequence's mean",
    read: "Every cluster's value divided by the mean of its own sequence's replicates, pooled over all sequences. The width around 1 is the replicate spread, cluster by cluster (its SD is shown in the legend).",
    bio: "Replicate clusters are the same molecule, so ideally all sit at 1. Clusters far from 1 are the ones measured off; a narrower orange curve means correction brought replicates of the same sequence closer together." },
  { file: "bases.png", alt: "Heatmaps of median signal by base and variable position, before, after and the change",
    read: "Rows: base; columns: variable position. Left and middle: median signal of sequences with that base there, as % away from all sequences. Right: the median change (corrected ÷ Feather) per cell, as % away from the overall change.",
    bio: "Real sequence effects (e.g. binding) show up as the same pattern before and after. Bleedover doesn't depend on sequence, so the change map should be flat; a pattern there means correction treated some sequences differently." },
  { file: "cv_by_cycle.png", alt: "Median normalized SD per cycle, Feather and corrected",
    read: "The median normalized SD over library members, in every corrected cycle.",
    bio: "Whatever correction does to the spread should be consistent across images and conditions; a change seen in one cycle only points to that image rather than to the method." },
];

/** The library metrics of one finished run, as views for the Results metric buttons. */
export async function libraryViews(run) {
  let result = null;
  try { result = await get("/api/library/result", { run }); } catch { /* not analysed yet */ }
  if (!result) return [{ id: "lib-setup", label: "Library", render: () => setupView(run) }];
  const c = result.config;
  const shown = result.per_cycle.find((r) => r.cycle === result.shown_cycle) || {};
  const src = (file) => `/api/report/file?${new URLSearchParams({ run, part: "library", name: file, v: result.created })}`;
  const [replicatesFig, mediansFig, cvFig, eachFig, withinFig, basesFig, cvCycleFig] = FIGURES;
  const summary = () => h("p", { class: "hint" }, `${c.family}: ${fmt.int(result.trusted_clusters)} trusted clusters in ` +
    `${fmt.int(result.replicates.members)} library members (median ${fmt.int(result.replicates.median_replicates)} replicates); ` +
    `${fmt.int(result.members_used)} members have ≥ ${c.min_replicates}. Signal = RFU above zero light.`);
  return [
    { id: "lib-cv", label: "Normalized SD", render: () => h("div", { class: "section" },
        keyLine(`Median normalized SD in ${result.shown_cycle}: ${fmt.num(shown.median_cv_feather)} → ${fmt.num(shown.median_cv_corrected)} ` +
          `(lower = replicates agree better) · ${fmt.int(shown.members)} members with ≥ ${c.min_replicates} trusted replicates`),
        figureView(src(cvFig.file), cvFig), summary()) },
    { id: "lib-each", label: "Each sequence", render: () => h("div", { class: "section" },
        keyLine(`${fmt.num(100 * (result.tighter_fraction ?? NaN), 0)}% of sequences have a lower normalized SD after correction (${result.shown_cycle})`),
        figureView(src(eachFig.file), eachFig)) },
    { id: "lib-within", label: "Within sequences", render: () => h("div", { class: "section" },
        keyLine(`Spread of clusters around their own sequence's mean (SD): Feather ${fmt.num(result.within_sd?.feather)} → corrected ${fmt.num(result.within_sd?.corrected)}`),
        figureView(src(withinFig.file), withinFig)) },
    ...(result.has_base_grid ? [{ id: "lib-bases", label: "Base heatmap", render: () => h("div", { class: "section" },
        figureView(src(basesFig.file), basesFig)) }] : []),
    { id: "lib-table", label: "Sequences", render: () => sequenceTable(run, result) },
    { id: "lib-cv-cycle", label: "SD by cycle", render: () => h("div", { class: "section" },
        figureView(src(cvCycleFig.file), cvCycleFig), perCycleTable(result)) },
    { id: "lib-medians", label: "Member signal", render: () => h("div", { class: "section" },
        keyLine(`Signal kept: ${fmt.num(100 * shown.median_ratio, 0)}% (median corrected ÷ Feather per member) · ` +
          `rank agreement ${fmt.num(shown.rank_agreement)} (Spearman; 1 = same order)`),
        figureView(src(mediansFig.file), mediansFig)) },
    { id: "lib-replicates", label: "Replicates", render: () => h("div", { class: "section" },
        figureView(src(replicatesFig.file), replicatesFig), summary(),
        h("p", { class: "hint" }, `Per-member statistics for every cycle: app_report/library/${result.files.table} in the run folder.`),
        h("p", {}, h("button", { class: "btn btn--text", type: "button", disabled: jobRunning, onclick: () => analyse(run) }, "Analyse again"))) },
  ];
}

const SEQ_COLUMNS = [
  { key: "member", label: "Sequence" },
  { key: "replicates", label: "Replicates", num: true, format: fmt.int },
  { key: "feather_median", label: "Signal, Feather", num: true, format: fmt.int },
  { key: "corrected_median", label: "Signal, corrected", num: true, format: fmt.int },
  { key: "signal_change_pct", label: "Signal change", num: true, format: (v) => `${v > 0 ? "+" : ""}${fmt.num(v, 1)}%` },
  { key: "feather_cv", label: "nSD, Feather", num: true, format: (v) => fmt.num(v, 3) },
  { key: "corrected_cv", label: "nSD, corrected", num: true, format: (v) => fmt.num(v, 3) },
  { key: "nsd_change", label: "nSD change", num: true, format: (v) => `${v > 0 ? "+" : ""}${fmt.num(v, 3)}` },
];

/** Every sequence, searchable and sortable: what the correction did to each one. */
function sequenceTable(run, result) {
  const search = h("input", { type: "text", placeholder: "Find a sequence, e.g. GGCA", "aria-label": "Find a sequence", spellcheck: "false" });
  const sortSelect = h("select", { "aria-label": "Sort by" }, ...SEQ_COLUMNS.slice(1).map((c) => h("option", { value: c.key }, `Sort: ${c.label}`)));
  const order = h("select", { "aria-label": "Order" }, h("option", { value: "desc" }, "high → low"), h("option", { value: "asc" }, "low → high"));
  sortSelect.value = "nsd_change";
  const info = h("p", { class: "hint" });
  const holder = h("div", { class: "table-wrap table-wrap--tall" });
  const load = debounce(async () => {
    try {
      const data = await get("/api/library/members", { run, q: search.value, sort: sortSelect.value, order: order.value, limit: 300 });
      info.textContent = `${fmt.int(data.total)} sequences${search.value ? " match" : ""} (${data.cycle}; showing ${Math.min(300, data.total)}). ` +
        "nSD = normalized SD of the sequence's replicate clusters; signal = median RFU above zero light.";
      holder.replaceChildren(table(SEQ_COLUMNS, data.rows, { compact: true }));
    } catch (error) { info.textContent = error.message; }
  }, 250);
  for (const el of [search, sortSelect, order]) el.addEventListener(el === search ? "input" : "change", load);
  load();
  return h("div", { class: "section" },
    keyLine("What the correction did to each sequence. Sort by nSD change to find the sequences it helped or hurt most."),
    h("div", { class: "field-row field-row--wrap" }, search, sortSelect, order), info, holder);
}

function perCycleTable(result) {
  return h("div", { class: "table-wrap" }, table([
    { key: "cycle", label: "Cycle" }, { key: "members", label: "Members", num: true, format: fmt.int },
    { key: "median_cv_feather", label: "Normalized SD, Feather", num: true, format: (v) => fmt.num(v) },
    { key: "median_cv_corrected", label: "Normalized SD, corrected", num: true, format: (v) => fmt.num(v) },
    { key: "median_ratio", label: "Signal kept", num: true, format: (v) => `${fmt.num(100 * v, 0)}%` },
    { key: "rank_agreement", label: "Rank agreement", num: true, format: (v) => fmt.num(v) },
  ], result.per_cycle, { compact: true }));
}

function setupView(run) {
  const ready = $("lib-enabled").checked && $("lib-template").value.trim();
  return h("div", { class: "section" },
    h("p", {}, ready
      ? "Group this run's clusters by library sequence and compare each sequence's replicate spread (normalized SD) before and after correction. It takes about a minute."
      : "Turn on Library analysis (card 3 on the left) and describe the library structure, then analyse this run."),
    ready ? h("p", {}, h("button", { class: "btn btn--filled", type: "button", disabled: jobRunning,
      onclick: () => analyse(run) }, "Analyse the library for this run")) : "");
}

const keyLine = (text) => h("p", { class: "view-key" }, text);

async function analyse(run) {
  try { bus.emit("job-started", await post("/api/library/run", { run, experiment: experiment.name })); }
  catch (error) { toast(error.message); }
}
