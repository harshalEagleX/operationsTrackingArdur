/**
 * Reports tab.
 *
 * Run renders inline. Export returns 202 immediately and the finished file
 * arrives as a notification with a download link — the browser never waits on
 * a 50,000-row Excel build, and neither does a web worker.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { toast } from "../core/toast.js";

export async function init() {
  const form = document.getElementById("report-form");
  if (!form) return;

  await populateReportList();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await runReport();
  });

  document.querySelectorAll("[data-export]").forEach((button) => {
    button.addEventListener("click", () => queueExport(button.dataset.export));
  });

  // The worker tells us when it is done.
  bus.on("notification.created", (notification) => {
    if (notification.notif_type === "report.ready") {
      toast.success("Your export is ready.", {
        action: {
          label: "Download",
          onClick: () => window.open(notification.link_url, "_blank"),
        },
        timeout: 0,
      });
    }
  });
}

async function populateReportList() {
  const select = document.getElementById("report-key");
  if (!select) return;

  const catalogue = await api.get("/reports/");
  select.textContent = "";
  catalogue.forEach((report) => {
    const option = document.createElement("option");
    option.value = report.key;
    option.textContent = report.label;
    select.appendChild(option);
  });
}

function currentFilters() {
  return {
    report_key: document.getElementById("report-key").value,
    date_from: document.getElementById("report-from").value || null,
    date_to: document.getElementById("report-to").value || null,
  };
}

async function runReport() {
  const table = document.getElementById("report-table");
  const head = document.getElementById("report-head");
  const body = table.querySelector("tbody");

  body.textContent = "";
  head.textContent = "";

  try {
    const response = await api.post("/reports/run/", currentFilters(), { raw: true });
    const payload = await response.json();

    if (!response.ok) {
      toast.error(payload.error?.message || "That report could not be run.");
      return;
    }

    const { columns, truncated } = payload.meta;
    const rows = payload.data;

    columns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column.label;
      head.appendChild(th);
    });

    // One fragment, one reflow — appending 5,000 rows individually is what
    // makes a report table feel broken.
    const fragment = document.createDocumentFragment();
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      columns.forEach((column) => {
        const td = document.createElement("td");
        const value = row[column.key];
        td.textContent = value === null || value === undefined ? "—" : value;
        tr.appendChild(td);
      });
      fragment.appendChild(tr);
    });
    body.appendChild(fragment);

    document.getElementById("report-truncated").hidden = !truncated;
    table.closest(".tab-panel").querySelector(".empty-state").hidden = rows.length > 0;
  } catch (error) {
    toast.error(error.message || "That report could not be run.");
  }
}

async function queueExport(format) {
  try {
    await api.post("/reports/export/", { ...currentFilters(), export_format: format });
    toast.info("Building your export — you'll get a notification when it's ready.");
  } catch (error) {
    toast.error(error.message || "Couldn't start that export.");
  }
}
