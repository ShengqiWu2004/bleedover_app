// Accessible tabs (WAI-ARIA tabs pattern): click or Left/Right/Home/End to switch.

export function initTabs(tablist) {
  const tabs = [...tablist.querySelectorAll('[role="tab"]')];

  function select(tab, focus = true) {
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    }
    if (focus) tab.focus();
    tablist.dispatchEvent(new CustomEvent("tabchange", { detail: tab.id }));
  }

  tablist.addEventListener("click", (e) => {
    const tab = e.target.closest('[role="tab"]');
    if (tab) select(tab);
  });
  tablist.addEventListener("keydown", (e) => {
    const i = tabs.indexOf(document.activeElement);
    const next = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    select(tabs[(next + tabs.length) % tabs.length]);
  });
  return { select: (id) => select(document.getElementById(id), false) };
}
