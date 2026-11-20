// Setup cards 1–2: choose the experiment folder, then find its FASTQ folder.

import { $, badge, bus, h, post, toast } from "./util.js";

const CHECK_LABELS = { "_metadata.csv": "_metadata.csv", "exp_details.txt": "exp_details.txt", ptirf: "ptirf/" };
let current = null;          // the inspected experiment
let jobRunning = false;

export function initExperiment(prefs) {
  $("exp-browse").addEventListener("click", browse);
  $("exp-path").addEventListener("keydown", (e) => { if (e.key === "Enter") typed(); });
  $("exp-path").addEventListener("change", typed);
  bus.on("job-state", (job) => { jobRunning = job.status === "running"; });

  for (const radio of document.querySelectorAll('input[name="fastq-mode"]')) {
    radio.checked = radio.value === prefs.fastq_mode;
    radio.addEventListener("change", () => resolveFastq({ fastq_mode: radio.value }));
  }
  $("fastq-library").value = prefs.fastq_library || "";
  $("fastq-library-row").hidden = prefs.fastq_mode !== "library";
  $("fastq-library").addEventListener("change", () => resolveFastq({ fastq_library: $("fastq-library").value.trim() }));
  $("fastq-browse").addEventListener("click", async () => {
    const { path } = await post("/api/browse", { purpose: "library" });
    if (path) {
      $("fastq-library").value = path;
      resolveFastq({ fastq_library: path, fastq_mode: "library" });
    }
  });
  $("fastq-id-form").addEventListener("submit", (e) => {
    e.preventDefault();
    if (!$("fastq-id").reportValidity()) return;
    resolveFastq({ flowcell_id: $("fastq-id").value.trim() });
  });
}

/** A run in progress is stopped only if the user agrees; returns whether to go on. */
async function leaveRunningJob() {
  if (!jobRunning) return true;
  const ok = confirm("A run is in progress. Choosing another experiment stops it. Images corrected so far are " +
    "kept, and you can resume the run later from Results. Stop the run and continue?");
  if (ok) await post("/api/cancel").catch(() => {});
  return ok;
}

async function browse() {
  if (!(await leaveRunningJob())) return;
  try {
    const { path } = await post("/api/browse", { purpose: "experiment" });
    if (path) choose(path);
  } catch (error) { toast(error.message); }
}

async function typed() {
  const path = $("exp-path").value.trim();
  if (!path || path === current?.path) return;           // Enter and the change that follows fire together
  if (!(await leaveRunningJob())) { $("exp-path").value = current?.path || ""; return; }
  choose(path);
}

/** The user picked an experiment: return every part of the page to its first state, then load it. */
function choose(path) {
  current = null;
  $("exp-checks").replaceChildren();
  $("exp-problems").replaceChildren();
  $("card-fastq").hidden = true;
  $("fastq-status").replaceChildren();
  $("fastq-id-form").hidden = true;
  $("fastq-id").value = "";
  $("layout").hidden = true;
  $("appbar-exp").hidden = true;
  document.title = "Bleedover Corrector";
  bus.emit("reset");
  bus.emit("experiment", null);
  open(path);
}

export async function open(path) {
  if (!path) return;
  $("exp-path").value = path;
  $("exp-summary").textContent = "Reading the folder…";
  $("exp-checks").replaceChildren();
  $("exp-problems").replaceChildren();
  try {
    current = await post("/api/inspect", { path });
  } catch (error) {
    $("exp-summary").textContent = "";
    $("exp-problems").replaceChildren(h("li", {}, error.message));
    $("layout").hidden = true;
    bus.emit("experiment", null);
    return;
  }
  renderChecks(current);
  renderFastq(current.fastq);
  $("card-fastq").hidden = false;
  $("layout").hidden = !current.cycles;      // the rest of the page appears once a real experiment is chosen
  bus.emit("experiment", current);
}

function renderChecks(info) {
  const optional = new Set(info.optional || []);           // missing optional files are a warning, not an error
  const items = Object.entries(info.checks).map(([name, ok]) =>
    h("li", {}, badge(ok ? "good" : optional.has(name) ? "warn" : "bad", ok || !optional.has(name) ? CHECK_LABELS[name] : `no ${CHECK_LABELS[name]}`)));
  if (info.cycles) {
    items.push(h("li", {}, badge(info.images_aligned ? "good" : "bad", `aligned ${info.images_aligned}/${info.images_total} images`)));
    items.push(h("li", {}, badge(info.feather.has_xy ? "good" : "bad", "results.feather")));
    items.push(h("li", {}, badge(info.alignment_matrix ? "good" : "warn", "alignment_matrix.json")));
  }
  $("exp-checks").replaceChildren(...items);
  const id = info.details.flowcell_id;
  $("exp-summary").textContent = info.cycles
    ? `${info.cycles.length} cycles · ${info.feather.rows.toLocaleString()} clusters · flowcell ${id || (info.details.file ? "not in exp_details.txt" : "unknown")}`
    : "";
  $("exp-problems").replaceChildren(...info.problems.map((p) => h("li", {}, p)),
    ...(info.notes || []).map((n) => h("li", { class: "note" }, n)));
  $("appbar-exp").textContent = info.name;
  $("appbar-exp").hidden = false;
  document.title = `${info.name} · Bleedover Corrector`;
}

async function resolveFastq(changes) {
  if (changes.fastq_mode) $("fastq-library-row").hidden = changes.fastq_mode !== "library";
  if (!current) {                       // no experiment yet: just remember the choice
    await post("/api/prefs", changes).catch(() => {});
    return;
  }
  $("fastq-status").className = "status-line status-line--neutral";
  $("fastq-status").textContent = "Looking for the FASTQ folder…";
  try {
    current.fastq = await post("/api/fastq", { path: current.path, ...changes });
    renderFastq(current.fastq);
    bus.emit("fastq", current.fastq);
  } catch (error) {
    $("fastq-status").className = "status-line status-line--warn";
    $("fastq-status").textContent = error.message;
  }
}

function renderFastq(result) {
  const status = $("fastq-status");
  const form = $("fastq-id-form");
  status.className = `status-line status-line--${result.found ? "good" : "warn"}`;
  const lines = [h("span", {}, h("span", { "aria-hidden": "true" }, result.found ? "✓ " : "! "), result.message)];
  if (result.found) {
    lines.push(h("span", { class: "path" }, result.path));
    lines.push(h("span", {}, `${result.samples.length} FASTQ file${result.samples.length === 1 ? "" : "s"}` +
      (result.flowcell_source === "typed" ? " · flowcell typed by you" : "")));
    if (result.alternatives?.length) lines.push(h("span", { class: "hint" }, `${result.alternatives.length} other matching folder(s); using the best match.`));
  }
  status.replaceChildren(...lines);
  // The ID box is the fallback: show it in library mode when nothing was found.
  form.hidden = result.mode !== "library" || result.found || !result.library;
  if (!form.hidden && !$("fastq-id").value) $("fastq-id").value = result.flowcell_id || result.flowcell_from_file || "";
}

export const experiment = () => current;
