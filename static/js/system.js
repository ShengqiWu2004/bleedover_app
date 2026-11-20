// "System" dialog (⚙): the built-in models (locked) and the user's saved calibrations (deletable).

import { $, bus, fmt, get, h, post, table, toast } from "./util.js";

export function initSystem() {
  $("system").addEventListener("click", async () => {
    $("system-dialog").showModal();
    render(await get("/api/system").catch((e) => ({ error: e.message })));
  });
  $("system-close").addEventListener("click", () => $("system-dialog").close());
}

const line = (g, o) => `${fmt.num(g)} × RFU ${o >= 0 ? "+" : "−"} ${fmt.int(Math.abs(o))}`;

function render(sys) {
  const body = $("system-body");
  if (sys.error) return body.replaceChildren(h("p", {}, sys.error));
  body.replaceChildren(
    h("h3", {}, "PSF models"),
    h("ul", { class: "locked-list", "aria-label": "Built-in PSF models (can't be deleted)" },
      ...sys.models.map((m) => h("li", { title: `${m.summary}\nBuilt-in calibrations: ${m.calibrations.map((c) => c.experiment).join(", ")}` },
        h("span", { "aria-hidden": "true" }, "🔒 "), m.label, h("span", { class: "sr-only" }, " (built in, can't be deleted)")))),
    h("h3", {}, "Your calibrations"),
    sys.calibrations.length
      ? h("div", { class: "table-wrap" }, table([
          { key: "experiment", label: "Experiment" },
          { key: "model", label: "Model", format: (v) => sys.models.find((m) => m.id === v)?.label.split(" (")[0] || v },
          { key: "gain", label: "counts =", format: (_, r) => line(r.gain, r.offset) },
          { key: "single_points", label: "Dots", num: true, format: fmt.int },
          { key: "created", label: "Saved" },
          { key: "id", label: "", format: (id, r) => h("button", { class: "btn btn--outlined", type: "button",
              "aria-label": `Delete calibration of ${r.experiment}`, onclick: () => remove(id, r) }, "Delete") },
        ], sys.calibrations, { compact: true }))
      : h("p", { class: "hint" }, "None yet. Calibrating an experiment saves one here, so later runs reuse it."),
    h("h3", {}, "Run folders"),
    h("p", {}, "Where the Results tab looks for correction runs. Add a folder of runs made with the scripts or notebooks (e.g. the repo's results/) to see them too."),
    h("ul", { class: "folders" },
      h("li", {}, h("code", {}, sys.paths.runs), h("span", { class: "hint" }, " (where this app saves new runs; always searched)")),
      ...sys.run_folders.map((f) => h("li", {}, h("code", {}, f), " ",
        h("button", { class: "btn btn--text", type: "button", "aria-label": `Stop using ${f}`, onclick: () => removeFolder(f) }, "Remove")))),
    h("p", {}, h("button", { class: "btn btn--tonal", type: "button", onclick: addFolder }, "Add run folder…")),
    h("h3", {}, "Where things are"),
    h("dl", { class: "kv" },
      h("dt", {}, "Saved calibrations"), h("dd", {}, h("code", {}, sys.paths.calibrations)),
      h("dt", {}, "Preferences"), h("dd", {}, h("code", {}, sys.paths.preferences)),
      h("dt", {}, "Computer"), h("dd", {}, `${sys.machine.cpus} cores, ${Math.round(sys.machine.memory_gb)} GB memory`)),
    h("p", {}, h("button", { class: "btn btn--outlined", type: "button", onclick: quit }, "Quit Bleedover Corrector")),
    h("p", { class: "hint" }, "The app also quits by itself 10 minutes after its last window closes, unless a run is going."));
}

async function quit() {
  const running = !$("status-cancel").hidden;
  if (!confirm(running ? "A run is going. Quit and stop it?" : "Quit Bleedover Corrector?")) return;
  await post("/api/quit").catch(() => {});
  document.body.replaceChildren(h("main", { class: "empty quit-screen" },
    h("h2", {}, "Bleedover Corrector has quit."), h("p", {}, "You can close this window.")));
}

async function addFolder() {
  try {
    const { path } = await post("/api/browse", { purpose: "runs" });
    if (path) { render(await get("/api/system")); bus.emit("run-folders-changed"); }
  } catch (error) { toast(error.message); }
}

async function removeFolder(path) {
  try { render(await post("/api/run-folders/remove", { path })); bus.emit("run-folders-changed"); }
  catch (error) { toast(error.message); }
}

async function remove(id, row) {
  if (!confirm(`Delete your calibration of ${row.experiment}? Runs already made keep their own copy.`)) return;
  try {
    render(await post("/api/calibrations/delete", { id }));
    bus.emit("calibrations-changed");
  } catch (error) { toast(error.message); }
}
