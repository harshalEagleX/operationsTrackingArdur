/**
 * Allocations tab — basic list with filters.
 *
 * Scaffold: lists allocations and reacts to live updates. The allocate/import
 * dialogs are left for the UI build-out; the API and the bulk-import Celery
 * task are both complete.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { toast } from "../core/toast.js";

export async function init() {
  if (!document.getElementById("allocations-table")) return;

  document
    .getElementById("allocation-search")
    ?.addEventListener("input", debounce(load, 300));
  document.getElementById("allocation-status-filter")?.addEventListener("change", load);
  document.getElementById("allocation-overdue-only")?.addEventListener("change", load);

  bus.on("allocation.updated", () => load());

  await load();
}

async function load() {
  const table = document.getElementById("allocations-table");
  const body = table.querySelector("tbody");
  const empty = table.closest(".tab-panel").querySelector(".empty-state");

  try {
    const rows = await api.get("/allocations/", {
      search: document.getElementById("allocation-search")?.value || "",
      status: document.getElementById("allocation-status-filter")?.value || "",
      overdue: document.getElementById("allocation-overdue-only")?.checked ? "true" : "",
    });
    const items = Array.isArray(rows) ? rows : [];

    body.textContent = "";
    items.forEach((allocation) => body.appendChild(renderRow(allocation)));
    empty.hidden = items.length > 0;
  } catch (error) {
    toast.error(error.message || "Couldn't load the allocations.");
  }
}

function renderRow(allocation) {
  const tr = document.createElement("tr");
  if (allocation.is_overdue) tr.classList.add("row-warning");

  [
    allocation.allocation_id,
    `${allocation.employee_name || allocation.employee_id}`,
    allocation.project || "—",
    allocation.quantity,
    `${allocation.progress_percent}%`,
    allocation.due_at ? new Date(allocation.due_at).toLocaleString() : "—",
    allocation.status.replace("_", " "),
  ].forEach((value) => {
    const td = document.createElement("td");
    td.textContent = value;
    tr.appendChild(td);
  });

  tr.appendChild(document.createElement("td"));
  return tr;
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}
