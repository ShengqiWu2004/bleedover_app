// Entry point: load saved preferences, wire up every part of the page, register the service worker.

import { experiment, initExperiment, open } from "./experiment.js";
import { initOverview } from "./overview.js";
import { initResults } from "./results.js";
import { initRunConfig } from "./runconfig.js";
import { initStatus } from "./status.js";
import { initSystem } from "./system.js";
import { initCleanup } from "./cleanup.js";
import { initLibrary } from "./library.js";
import { initTabs } from "./tabs.js";
import { $, bus, get, toast } from "./util.js";
import { initViewer, onShow as showViewer } from "./viewer.js";

async function main() {
  const { prefs, machine } = await get("/api/state");
  const tabs = initTabs(document.querySelector('[role="tablist"]'));
  document.querySelector('[role="tablist"]').addEventListener("tabchange", (e) => {
    if (e.detail === "tab-viewer") showViewer();
  });

  initOverview();
  initResults();
  initViewer();
  initRunConfig(prefs, machine);
  initExperiment(prefs);
  initStatus();
  initSystem();
  initCleanup();
  initLibrary();
  bus.on("calibrations-changed", () => experiment() && open(experiment().path));

  bus.on("job-started", () => tabs.select("tab-overview"));
  bus.on("reset", () => tabs.select("tab-overview"));
  bus.on("job-finished", () => {
    tabs.select("tab-results");
    if (experiment()) open(experiment().path);   // re-read: a calibration adds a model, the run adds a report
  });
  $("help").addEventListener("click", () => $("help-dialog").showModal());
  $("help-close").addEventListener("click", () => $("help-dialog").close());
  installPrompt();
}

/** Installable app (PWA): offer "Install app" where the browser supports it. */
function installPrompt() {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  let deferred = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferred = e;
    $("install").hidden = false;
  });
  $("install").addEventListener("click", async () => {
    $("install").hidden = true;
    await deferred?.prompt();
    deferred = null;
  });
}

main().catch((error) => toast(`Couldn't start: ${error.message}`));
