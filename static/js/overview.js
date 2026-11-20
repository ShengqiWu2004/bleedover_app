// "Experiment" tab: what the folder holds, in biological terms (samples, which should glow, which cycles).

import { $, badge, bus, fmt, h, post, table } from "./util.js";

export function initOverview() {
  bus.on("experiment", render);
  bus.on("fastq", () => current && loadSamples(current));
}

let current = null;

function render(info) {
  current = info;
  const root = $("overview");
  if (!info) return root.replaceChildren();
  const d = info.details;
  const parts = [
    h("section", { class: "section" },
      h("h2", {}, info.name),
      h("dl", { class: "kv" },
        h("dt", {}, "Date"), h("dd", {}, info.date || "–"),
        h("dt", {}, "Performed by"), h("dd", {}, info.person || "–"),
        h("dt", {}, "Flowcell"), h("dd", {}, d.flowcell_id || (d.file ? "not in exp_details.txt" : "– (no exp_details.txt)")),
        h("dt", {}, "Channel"), h("dd", {}, info.channel || "–"),
        h("dt", {}, "Cycles"), h("dd", {}, info.cycles ? `${info.cycles.length} (${fmt.int(info.images_aligned)} of ${fmt.int(info.images_total)} images aligned)` : "–"),
        h("dt", {}, "Clusters"), h("dd", {}, info.feather ? `${fmt.int(info.feather.rows)} (≈${fmt.int(info.clusters_per_tile)} per tile)` : "–")),
      d.notes ? h("div", { class: "notes", "aria-label": "Notes from exp_details.txt" }, d.notes) : null),
  ];
  if (info.cycles) {
    parts.push(h("section", { class: "section" },
      h("h3", {}, "Samples on the flowcell"),
      h("div", { id: "samples" }, h("p", { class: "hint" }, info.feather?.exists
        ? "Counting clusters per sample…" : "No img_results/results.feather yet: samples appear after MAPA's intensity extraction."))));
    parts.push(h("section", { class: "section" },
      h("h3", {}, "Cycles"),
      h("div", { class: "table-wrap" }, table(
        [{ key: "cycle", label: "Cycle" }, { key: "folder", label: "Image folder" }, { key: "type", label: "Type" },
         { key: "aligned_tiles", label: "Aligned tiles", format: (v) => `${v.length} of ${info.device_tiles.length}` }],
        info.cycles, { compact: true }))));
    if (info.feather?.exists) loadSamples(info);
  }
  root.replaceChildren(...parts);
}

async function loadSamples(info) {
  const fastqSamples = info.fastq?.found ? info.fastq.samples.map((s) => s.sample) : null;
  try {
    const { origins } = await post("/api/origins", { path: info.path, fastq_samples: fastqSamples });
    if (current !== info) return;
    bus.emit("origins", origins);
    const types = Object.keys(info.alignment_matrix || {});
    const glow = (row) => {
      const states = [...new Set(types.map((t) => row.lit[t]))];
      if (!types.length || states.includes(undefined) || states.includes(null)) return badge("neutral", "unknown");
      if (states.length > 1) return badge("neutral", "some cycles");
      return states[0] ? badge("good", "yes") : badge("neutral", "no");
    };
    const columns = [
      { key: "family", label: "Sample" }, { key: "role_label", label: "Kind" },
      { key: "clusters", label: "Clusters", num: true, format: fmt.int },
      { key: "lit", label: "Should glow", format: (_, row) => glow(row) },
    ];
    if (fastqSamples) columns.push({ key: "in_fastq", label: "FASTQ file", format: (v) => (v ? badge("good", "found") : badge("warn", "missing")) });
    $("samples")?.replaceChildren(h("div", { class: "table-wrap" }, table(columns, origins, { compact: true })));
  } catch (error) {
    $("samples")?.replaceChildren(h("p", { class: "hint" }, `Couldn't read samples: ${error.message}`));
  }
}
