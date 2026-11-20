// Small shared helpers: API calls, DOM building, formatting, a tiny event bus.

export const $ = (id) => document.getElementById(id);

/** fetch JSON; throws Error(message from the server) on failure. */
async function request(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `${response.status} ${response.statusText}`);
  return data;
}
export const get = (path, params = {}) => request("GET", `${path}?${new URLSearchParams(params)}`);
export const post = (path, body = {}) => request("POST", path, body);

/** h("p", {class: "x"}, "text", child) — builds elements without innerHTML. */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (key === "class") el.className = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

/** Fill a fieldset of toggle chips; returns a function that reads the checked values. */
export function chips(fieldset, values, checked, labelOf = (v) => v) {
  fieldset.querySelectorAll("label").forEach((l) => l.remove());
  const on = new Set(checked);
  for (const value of values) {
    fieldset.append(h("label", {}, h("input", { type: "checkbox", value, checked: on.has(value) }), h("span", {}, labelOf(value))));
  }
  return () => [...fieldset.querySelectorAll("input:checked")].map((i) => i.value);
}

export function table(columns, rows, { compact = false, current } = {}) {
  return h("table", { class: compact ? "table table--compact" : "table" },
    h("thead", {}, h("tr", {}, columns.map((c) => h("th", { class: c.num ? "num" : null, scope: "col" }, c.label)))),
    h("tbody", {}, rows.map((row) => h("tr", { class: current && current(row) ? "is-current" : null },
      columns.map((c) => h("td", { class: c.num ? "num" : null }, c.format ? c.format(row[c.key], row) : row[c.key] ?? "–"))))));
}

/** One figure with "How to read it" / "What it means biologically" captions. */
export function figureView(src, f) {
  return h("figure", { class: "figure figure--single", "aria-label": f.title || f.alt },
    h("img", { src, alt: f.alt, decoding: "async", width: 820, height: 420 }),
    h("figcaption", {}, h("p", {}, h("strong", {}, "How to read it. "), f.read),
      h("p", {}, h("strong", {}, "What it means biologically. "), f.bio)));
}

export function badge(kind, text) {
  const icon = { good: "✓", warn: "!", bad: "✕", neutral: "•" }[kind];
  return h("span", { class: `badge badge--${kind}` }, h("span", { "aria-hidden": "true" }, icon), text);
}

export const fmt = {
  int: (v) => (v === null || v === undefined ? "–" : Math.round(v).toLocaleString()),
  num: (v, d = 2) => (v === null || v === undefined ? "–" : Number(v).toFixed(d)),
  signed: (v) => (v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${Math.round(v).toLocaleString()}`),
  duration(seconds) {
    if (seconds === null || seconds === undefined || !isFinite(seconds)) return "–";
    const s = Math.max(0, Math.round(seconds));
    if (s < 60) return `${s} s`;
    const m = Math.round(s / 60);
    if (m < 60) return `${m} min`;
    return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
  },
};

let toastTimer;
export function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 6000);
}

/** Minimal pub/sub so modules don't import each other. */
const listeners = {};
export const bus = {
  on: (name, fn) => (listeners[name] ||= []).push(fn),
  emit: (name, data) => (listeners[name] || []).forEach((fn) => fn(data)),
};

export function debounce(fn, ms = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
