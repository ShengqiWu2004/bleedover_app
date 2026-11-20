// 🧹 Clean-up dialog: the browsed experiment's runs, finished (green) or incomplete (red); delete or rebuild reports.

import { $, bus, get, h, post, table, toast } from "./util.js";

let experiment = null;
let jobRunning = false;

export function initCleanup() {
  bus.on("experiment", (info) => { experiment = info?.cycles ? info : null; $("clean").disabled = !experiment; });
  bus.on("job-state", (job) => { jobRunning = job.status === "running"; });
  $("clean").addEventListener("click", async () => {
    $("clean-dialog").showModal();
    render((await get("/api/runs", { experiment: experiment.name }).catch((e) => ({ error: e.message }))));
  });
  $("clean-close").addEventListener("click", () => $("clean-dialog").close());
}

const STATE = {
  done: ["done", "✓", "Finished"],
  stopped: ["stopped", "✕", "Incomplete"],
  running: ["running", "●", "Running"],
};

function render(data) {
  const body = $("clean-body");
  $("clean-title").textContent = `Runs of ${experiment.name}`;
  if (data.error) return body.replaceChildren(h("p", {}, data.error));
  const runs = data.runs;
  const incomplete = runs.filter((r) => r.status === "stopped");
  const state = (r) => {
    const [kind, icon, label] = STATE[r.status];
    return h("span", { class: `run-state run-state--${kind}` }, h("span", { "aria-hidden": "true" }, icon), label);
  };
  const actions = (r) => h("span", {},
    r.status === "done" ? h("button", { class: "btn btn--text", type: "button", disabled: jobRunning,
      onclick: () => rebuild(r) }, r.has_report ? "Rebuild report" : "Build report") : "",
    r.status !== "running" ? h("button", { class: "btn btn--outlined", type: "button",
      "aria-label": `Delete run ${r.run}`, onclick: () => remove([r]) }, "Delete") : "");
  body.replaceChildren(
    h("p", {}, "Only this experiment's runs are listed. Deleting a run removes its folder: corrected images, report and settings. It can't be undone."),
    runs.length
      ? h("div", { class: "table-wrap" }, table([
          { key: "status", label: "State", format: (_, r) => state(r) },
          { key: "started", label: "Started", format: (v, r) => (v || r.run.slice(0, 13)).slice(0, 16) },
          { key: "method", label: "Method" },
          { key: "images_done", label: "Images", num: true,
            format: (v, r) => (r.status === "done" || !r.images_total ? `${v}` : `${v} of ${r.images_total}`) },
          { key: "made_by", label: "Made by" },
          { key: "run", label: "", format: (_, r) => actions(r) },
        ], runs, { compact: true }))
      : h("p", { class: "hint" }, "This experiment has no runs."),
    incomplete.length
      ? h("div", { class: "dialog-actions" }, h("button", { class: "btn btn--filled", type: "button",
          onclick: () => remove(incomplete) }, `Delete all incomplete (${incomplete.length})`))
      : h("p", { class: "hint" }, "No incomplete runs."));
}

async function remove(list) {
  const what = list.length === 1 ? `the run from ${(list[0].started || list[0].run).slice(0, 16)} (${list[0].method}, ${list[0].images_done} images)`
    : `${list.length} incomplete runs`;
  if (!confirm(`Delete ${what}? Its folder and everything in it are removed for good.`)) return;
  let data = null;
  for (const r of list) {
    try { data = await post("/api/runs/delete", { run: r.run, experiment: experiment.name }); }
    catch (error) { toast(error.message); }
  }
  if (data) render(data);
  bus.emit("runs-changed");
}

async function rebuild(r) {
  try {
    bus.emit("job-started", await post("/api/report/build", { run: r.run }));
    $("clean-dialog").close();
  } catch (error) { toast(error.message); }
}
