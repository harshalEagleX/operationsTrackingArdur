/**
 * Supervisor dashboard.
 *
 * Loads the headline metrics and lazily imports each tab's module the first
 * time that tab is opened — nobody pays for the reports code while looking at
 * the employee list.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { toast } from "../core/toast.js";

const loaded = new Set();

async function init() {
  await loadMetrics();

  bus.on("tab:switch", (tab) => loadTab(tab));

  const active = document.querySelector('[data-tab][aria-selected="true"]');
  loadTab(active?.dataset.tab || "employees");

  // Anything that changes the floor changes the numbers.
  ["work.session.started", "work.session.completed", "break.started", "break.ended"].forEach(
    (event) => bus.on(event, debounce(loadMetrics, 2000)),
  );
}

async function loadMetrics() {
  try {
    const metrics = await api.get("/reports/metrics/");
    Object.entries(metrics).forEach(([key, value]) => {
      const element = document.querySelector(`[data-metric="${key}"]`);
      if (element) element.textContent = value;
    });
  } catch {
    toast.error("Couldn't refresh the dashboard figures.");
  }
}

async function loadTab(tab) {
  if (loaded.has(tab)) return;
  loaded.add(tab);

  const modules = {
    employees: () => import("./employees.js"),
    masters: () => import("./masters.js"),
    allocations: () => import("./allocations.js"),
    reports: () => import("./reports.js"),
  };

  const load = modules[tab];
  if (!load) return;

  try {
    const module = await load();
    module.init?.();
  } catch (error) {
    loaded.delete(tab); // let a retry work
    console.error(`could not load the ${tab} tab`, error);
    toast.error(`Couldn't load ${tab}. Refresh the page and try again.`);
  }
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

document.addEventListener("DOMContentLoaded", init);
