/**
 * Tab switching, shared by every screen.
 *
 * Keeps aria-selected in sync and reflects the active tab in the URL, so a
 * link to ?tab=reports opens the right panel — which the notification links
 * rely on.
 */

import { bus } from "./bus.js";

export function initTabs(root = document) {
  const groups = new Map();

  root.querySelectorAll("[data-tab]").forEach((button) => {
    const container = button.closest(".tabs") || root;
    if (!groups.has(container)) groups.set(container, []);
    groups.get(container).push(button);

    button.addEventListener("click", () => activate(button, container));
  });

  // Deep link: ?tab=reports
  const requested = new URLSearchParams(window.location.search).get("tab");
  if (requested) {
    const target = root.querySelector(`[data-tab="${CSS.escape(requested)}"]`);
    if (target) activate(target, target.closest(".tabs") || root);
  }

  // Sub-tabs (master data types) use the same mechanism, different attribute.
  root.querySelectorAll("[data-master]").forEach((button) => {
    button.addEventListener("click", () => {
      button
        .closest(".subtabs")
        ?.querySelectorAll("[data-master]")
        .forEach((b) => b.setAttribute("aria-selected", String(b === button)));
      bus.emit("masters:switch", button.dataset.master);
    });
  });
}

function activate(button, container) {
  const name = button.dataset.tab;

  container.querySelectorAll("[data-tab]").forEach((other) => {
    other.setAttribute("aria-selected", String(other === button));
  });

  document.querySelectorAll("[data-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== name;
  });

  const url = new URL(window.location);
  url.searchParams.set("tab", name);
  window.history.replaceState({}, "", url);

  bus.emit("tab:switch", name);
}
