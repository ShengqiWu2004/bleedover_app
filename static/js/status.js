// Bottom status bar: live progress from the server (server-sent events), ETA, cancel, and the log.

import { $, bus, fmt, post, toast } from "./util.js";

const STAGES = { calibrate: "Calibrating the model", correct: "Correcting images", report: "Building the report", library: "Analysing the library" };
let last = { status: "idle" };
let dismissed = null;        // a finished job the user has moved on from: the bar shows "Ready" instead

export function initStatus() {
  const source = new EventSource("/api/events");
  let first = true;
  source.onmessage = (e) => {
    const job = JSON.parse(e.data);
    if (first && job.status !== "running") dismissed = job.started_at;   // a fresh window starts at "Ready"
    first = false;
    render(job);
  };
  bus.on("reset", () => { dismissed = last.started_at; render(last); });
  $("status-cancel").addEventListener("click", async () => {
    if (!confirm("Stop the run? Images corrected so far are kept, and you can resume it later from Results.")) return;
    try { render(await post("/api/cancel")); } catch (error) { toast(error.message); }
  });
  $("status-log").addEventListener("click", () => { $("log-dialog").showModal(); scrollLog(); });
  $("log-close").addEventListener("click", () => $("log-dialog").close());
  bus.on("job-started", render);
}

function scrollLog() {
  const pre = $("log-text");
  pre.scrollTop = pre.scrollHeight;
}

function render(job) {
  const was = last.status;
  last = job;
  bus.emit("job-state", job);
  if (job.status !== "running" && job.started_at && job.started_at === dismissed) job = { status: "idle", log: job.log };
  const progress = $("status-progress");
  progress.classList.toggle("is-failed", job.status === "failed");
  progress.classList.toggle("is-done", job.status === "done");
  $("status-cancel").hidden = job.status !== "running";
  $("log-text").textContent = (job.log || []).join("\n");
  if ($("log-dialog").open) scrollLog();

  if (job.status === "idle") {
    $("status-stage").textContent = "Ready";
    $("status-detail").textContent = "";
    $("status-time").textContent = "";
    progress.value = 0;
    return;
  }
  const stages = job.stages || [];
  const n = Math.max(stages.length, 1);
  const index = Math.max(stages.indexOf(job.stage), 0);
  const within = job.total ? job.done / job.total : 0;
  if (job.status === "running") {
    $("status-stage").textContent = `${STAGES[job.stage] || job.stage} · step ${index + 1} of ${n}` + (job.total ? ` · ${job.done}/${job.total}` : "");
    $("status-detail").textContent = job.last || "";
    progress.value = (index + within) / n;
    $("status-time").textContent = `${job.eta_seconds != null ? `≈ ${fmt.duration(job.eta_seconds)} left · ` : ""}${fmt.duration(job.elapsed_seconds)} elapsed`;
  } else {
    const label = { done: "Finished", failed: "Failed", cancelled: "Cancelled" }[job.status] || job.status;
    $("status-stage").textContent = `${label}: ${job.experiment || ""}`;
    $("status-detail").textContent = job.status === "failed" ? job.error || "" : job.status === "done" ? "Report ready in the Results tab." : "Images corrected so far are kept; resume it from Results.";
    $("status-time").textContent = `took ${fmt.duration(job.elapsed_seconds)}`;
    progress.value = job.status === "done" ? 1 : progress.value;
  }
  if (job.status !== was) {
    $("status-live").textContent = $("status-stage").textContent;
    if (was === "running" && job.status === "done") bus.emit("job-finished", job);
  }
}
