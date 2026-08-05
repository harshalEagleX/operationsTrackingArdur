/**
 * Master data tab — basic list per type.
 *
 * Scaffold: lists whichever master type is selected. Create/edit dialogs are
 * left for the UI build-out; the API is complete and admin-gated.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { toast } from "../core/toast.js";

const TYPES = {
  worktypes: {
    path: "/masters/worktypes/",
    columns: [["work_type", "Work type"], ["description", "Description"],
              ["standard_rate", "Rate/hr"], ["is_active", "Active"]],
  },
  projects: {
    path: "/masters/projects/",
    columns: [["project_name", "Project"], ["project_code", "Code"],
              ["client_name", "Client"], ["is_active", "Active"]],
  },
  clientcodes: {
    path: "/masters/clientcodes/",
    columns: [["client_code", "Client code"], ["client_name", "Client"],
              ["project", "Project"], ["is_active", "Active"]],
  },
  shifts: {
    path: "/masters/shifts/",
    columns: [["shift_name", "Shift"], ["start_time", "Start"],
              ["end_time", "End"], ["is_active", "Active"]],
  },
};

let current = "worktypes";

export async function init() {
  if (!document.getElementById("masters-table")) return;

  bus.on("masters:switch", (type) => {
    current = type;
    load();
  });

  document.getElementById("masters-active-only")?.addEventListener("change", load);

  await load();
}

async function load() {
  const config = TYPES[current];
  const table = document.getElementById("masters-table");
  const head = document.getElementById("masters-head");
  const body = table.querySelector("tbody");
  const empty = table.closest(".tab-panel").querySelector(".empty-state");

  try {
    const activeOnly = document.getElementById("masters-active-only")?.checked;
    const rows = await api.get(config.path, activeOnly ? { active: "true" } : {});
    const items = Array.isArray(rows) ? rows : [];

    head.textContent = "";
    config.columns.forEach(([, label]) => {
      const th = document.createElement("th");
      th.textContent = label;
      head.appendChild(th);
    });

    body.textContent = "";
    items.forEach((item) => {
      const tr = document.createElement("tr");
      config.columns.forEach(([key]) => {
        const td = document.createElement("td");
        const value = item[key];
        td.textContent =
          typeof value === "boolean" ? (value ? "Yes" : "No") : (value ?? "—");
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });

    empty.hidden = items.length > 0;
  } catch (error) {
    toast.error(error.message || "Couldn't load that list.");
  }
}
