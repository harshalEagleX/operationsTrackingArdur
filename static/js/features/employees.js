/**
 * Employees tab — basic list and search.
 *
 * Scaffold: renders the roster and wires the search/filter controls. Add/edit
 * dialogs are left for the UI build-out; the API behind them
 * (POST/PATCH /api/v1/auth/employees/) is complete and permission-checked.
 */

import { api } from "../core/api.js";
import { store } from "../core/store.js";
import { toast } from "../core/toast.js";

export async function init() {
  const table = document.getElementById("employees-table");
  if (!table) return;

  document
    .getElementById("employee-search")
    ?.addEventListener("input", debounce(load, 300));
  document.getElementById("employee-role-filter")?.addEventListener("change", load);

  await load();
}

async function load() {
  const table = document.getElementById("employees-table");
  const body = table.querySelector("tbody");
  const empty = table.closest(".tab-panel").querySelector(".empty-state");

  try {
    const rows = await api.get("/auth/employees/", {
      search: document.getElementById("employee-search")?.value || "",
      role: document.getElementById("employee-role-filter")?.value || "",
    });

    body.textContent = "";
    const items = Array.isArray(rows) ? rows : [];

    items.forEach((employee) => body.appendChild(renderRow(employee)));
    empty.hidden = items.length > 0;
  } catch (error) {
    toast.error(error.message || "Couldn't load the employee list.");
  }
}

function renderRow(employee) {
  const tr = document.createElement("tr");

  // Every cell uses textContent — names and project titles are user input.
  [
    employee.employee_id,
    employee.name,
    employee.role,
    employee.project || "—",
    employee.shift || "—",
    employee.status,
  ].forEach((value) => {
    const td = document.createElement("td");
    td.textContent = value;
    tr.appendChild(td);
  });

  const actions = document.createElement("td");
  if (store.isSupervisor) {
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "btn btn-link";
    edit.textContent = "Edit";
    edit.dataset.employeeId = employee.employee_id;
    actions.appendChild(edit);
  }
  tr.appendChild(actions);

  return tr;
}

function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}
