/**
 * The who's-on-the-floor rail.
 *
 * Fetches the full roster once, then applies `presence.changed` deltas. A
 * status change is one dataset write and zero DOM rebuilds — the dot colour
 * is entirely CSS driven off the attribute.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { store } from "../core/store.js";

const LABELS = {
  online: "Online",
  working: "Working",
  on_break: "On break",
  busy: "Busy",
  idle: "Idle",
  offline: "Offline",
};

const ORDER = ["working", "on_break", "online", "busy", "idle", "offline"];

export async function initPresence() {
  bus.on("presence.changed", ({ emp_id, status }) => {
    store.presence.set(emp_id, status);
    applyStatus(emp_id, status);
    renderCount();
  });

  // Re-sync after a reconnect: `presence.changed` is transient and is not
  // replayed, so a gap means the rail could be stale.
  bus.on("realtime:open", () => loadRoster());

  await loadRoster();
}

async function loadRoster() {
  const list = document.getElementById("presence-list");
  if (!list) return;

  try {
    const roster = await api.get("/presence/");

    roster.sort(
      (a, b) =>
        ORDER.indexOf(a.status) - ORDER.indexOf(b.status) ||
        a.name.localeCompare(b.name),
    );

    list.textContent = "";
    roster.forEach((entry) => {
      store.presence.set(entry.emp_id, entry.status);
      list.appendChild(renderEntry(entry));
    });

    renderCount();
  } catch {
    // The rail is ambient information. A failure here must not interrupt
    // whatever the user is actually doing.
  }
}

function renderEntry(entry) {
  const item = document.createElement("li");
  item.className = "presence-item";

  const dot = document.createElement("span");
  dot.dataset.presence = entry.emp_id;
  dot.dataset.status = entry.status;
  dot.title = LABELS[entry.status] || entry.status;
  item.appendChild(dot);

  const name = document.createElement("span");
  name.className = "presence-name";
  name.textContent = entry.name;
  item.appendChild(name);

  if (entry.custom_status) {
    const custom = document.createElement("span");
    custom.className = "presence-custom";
    custom.textContent = entry.custom_status;
    item.appendChild(custom);
  }

  return item;
}

function applyStatus(empId, status) {
  document
    .querySelectorAll(`[data-presence="${CSS.escape(empId)}"]`)
    .forEach((element) => {
      element.dataset.status = status;
      element.title = LABELS[status] || status;
    });
}

function renderCount() {
  const counter = document.getElementById("presence-count");
  if (!counter) return;

  const online = [...store.presence.values()].filter((s) => s !== "offline").length;
  counter.textContent = `(${online})`;
}
