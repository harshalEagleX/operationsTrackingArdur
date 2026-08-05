/**
 * Employee dashboard.
 *
 * The timer is driven off the server's elapsed value plus local wall-clock
 * drift since the last sync — never off the browser's own start time. The
 * server is the only clock that counts, and this keeps the display honest
 * even if the machine's clock is wrong.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { store } from "../core/store.js";
import { toast } from "../core/toast.js";

import { initWork } from "./userdashboard-work.js";
import { initBreaks } from "./userdashboard-breaks.js";

document.addEventListener("DOMContentLoaded", async () => {
  await store.loadMasters();
  populateSelects();

  await Promise.all([initWork(), initBreaks(), loadTasks(), loadSessions()]);

  bus.on("tab:switch", (tab) => {
    if (tab === "tasks") loadTasks();
    if (tab === "sessions") loadSessions();
    if (tab === "feedback") loadFeedback();
  });

  bus.on("allocation.updated", loadTasks);
  bus.on("work.session.completed", loadSessions);
});

function populateSelects() {
  const { projects, work_types: workTypes, client_codes: clientCodes } = store.masters;

  store.fillSelect(document.getElementById("project"), projects, {
    valueKey: "project_name",
    labelKey: "project_name",
    placeholder: "Select a project",
  });
  store.fillSelect(document.getElementById("work_type"), workTypes, {
    valueKey: "work_type",
    labelKey: "work_type",
    placeholder: "Select a work type",
  });
  store.fillSelect(document.getElementById("client_code"), clientCodes, {
    valueKey: "client_code",
    labelKey: "client_code",
    placeholder: "Optional",
  });
}

async function loadTasks() {
  const table = document.getElementById("tasks-table");
  if (!table) return;

  const body = table.querySelector("tbody");
  const empty = table.closest(".tab-panel").querySelector(".empty-state");

  try {
    const tasks = await api.get("/allocations/mine/");
    body.textContent = "";

    (tasks || []).forEach((task) => {
      const tr = document.createElement("tr");
      [
        task.allocation_id,
        task.project || "—",
        task.quantity,
        `${task.progress_percent}%`,
        task.due_at ? new Date(task.due_at).toLocaleString() : "—",
        task.status.replace("_", " "),
      ].forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      tr.appendChild(document.createElement("td"));
      body.appendChild(tr);
    });

    empty.hidden = (tasks || []).length > 0;
  } catch {
    toast.error("Couldn't load your tasks.");
  }
}

async function loadSessions() {
  const table = document.getElementById("sessions-table");
  if (!table) return;

  const body = table.querySelector("tbody");
  const empty = table.closest(".tab-panel").querySelector(".empty-state");

  try {
    const sessions = await api.get("/tracking/sessions/", { today: "true" });
    const items = Array.isArray(sessions) ? sessions : [];

    body.textContent = "";
    items.forEach((session) => {
      const tr = document.createElement("tr");
      [
        new Date(session.start_time).toLocaleTimeString(),
        session.project || "—",
        session.work_type || "—",
        session.work_units,
        formatDuration(session.total_time),
        session.average_time ? `${session.average_time}s` : "—",
      ].forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });

    empty.hidden = items.length > 0;
  } catch {
    toast.error("Couldn't load today's work.");
  }
}

async function loadFeedback() {
  const container = document.getElementById("feedback-list");
  if (!container) return;

  const empty = container.closest(".tab-panel").querySelector(".empty-state");

  try {
    const feedback = await api.get("/feedback/mine/");
    const items = Array.isArray(feedback) ? feedback : [];

    container.textContent = "";
    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = `feedback-card severity-${item.severity}`;

      const heading = document.createElement("h3");
      heading.textContent = item.subject;
      card.appendChild(heading);

      if (item.description) {
        const body = document.createElement("p");
        body.textContent = item.description;
        card.appendChild(body);
      }

      const meta = document.createElement("p");
      meta.className = "feedback-meta";
      meta.textContent = `${item.feedback_type} · ${item.created_by_name || item.created_by} · ${new Date(item.created_at).toLocaleDateString()}`;
      card.appendChild(meta);

      if (!item.is_acknowledged) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "btn btn-primary";
        button.textContent = "Acknowledge";
        button.addEventListener("click", async () => {
          await api.post(`/feedback/${item.id}/acknowledge/`, { response: "" });
          toast.success("Acknowledged.");
          loadFeedback();
        });
        card.appendChild(button);
      }

      container.appendChild(card);
    });

    empty.hidden = items.length > 0;
  } catch {
    toast.error("Couldn't load your feedback.");
  }
}

export function formatDuration(seconds) {
  if (!seconds) return "—";
  const total = Math.floor(seconds);
  const h = String(Math.floor(total / 3600)).padStart(2, "0");
  const m = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const s = String(total % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}
