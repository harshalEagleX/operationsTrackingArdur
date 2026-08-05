/**
 * The work timer.
 *
 * The displayed value is the server's `live_elapsed_seconds` plus however long
 * has passed locally since that response arrived. It is a display convenience
 * only — when the session is ended, the server recomputes the duration from
 * its own clock and ignores anything the browser thinks.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { toast } from "../core/toast.js";
import { formatDuration } from "./userdashboard.js";

let session = null;
let syncedAt = 0;
let ticker = null;

export async function initWork() {
  document.getElementById("start-session-form")?.addEventListener("submit", start);
  document.getElementById("pause-btn")?.addEventListener("click", pause);
  document.getElementById("resume-btn")?.addEventListener("click", resume);
  document.getElementById("end-btn")?.addEventListener("click", promptEnd);

  bus.on("work.session.started", refresh);
  bus.on("work.session.completed", refresh);

  await refresh();
}

async function refresh() {
  try {
    session = await api.get("/tracking/sessions/current/");
    syncedAt = Date.now();
    render();
  } catch {
    // Leave the last known state on screen rather than blanking it.
  }
}

function render() {
  const idle = document.getElementById("work-idle");
  const running = document.getElementById("work-running");
  if (!idle || !running) return;

  idle.hidden = Boolean(session);
  running.hidden = !session;

  if (!session) {
    stopTicker();
    return;
  }

  document.getElementById("pause-btn").hidden = session.is_paused;
  document.getElementById("resume-btn").hidden = !session.is_paused;

  const meta = document.getElementById("work-meta");
  meta.textContent = [session.project, session.work_type, session.batch]
    .filter(Boolean)
    .join(" · ") + (session.is_paused ? " · paused" : "");

  startTicker();
}

function startTicker() {
  stopTicker();
  tick();
  ticker = setInterval(tick, 1000);
}

function stopTicker() {
  if (ticker) clearInterval(ticker);
  ticker = null;
}

function tick() {
  const display = document.getElementById("work-timer");
  if (!display || !session) return;

  // While paused the server's number is frozen, so do not add local drift.
  const drift = session.is_paused ? 0 : (Date.now() - syncedAt) / 1000;
  display.textContent = formatDuration(session.live_elapsed_seconds + drift);
}

async function start(event) {
  event.preventDefault();
  const form = event.target;
  const data = new FormData(form);

  try {
    session = await api.post("/tracking/sessions/", {
      project: data.get("project"),
      work_type: data.get("work_type"),
      client_code: data.get("client_code") || "",
      batch: data.get("batch") || "",
    });
    syncedAt = Date.now();
    render();
    toast.success("Work session started.");
  } catch (error) {
    toast.error(error.message || "Couldn't start that session.");
  }
}

async function pause() {
  try {
    session = await api.post(`/tracking/sessions/${session.id}/pause/`);
    syncedAt = Date.now();
    render();
  } catch (error) {
    toast.error(error.message || "Couldn't pause the session.");
  }
}

async function resume() {
  try {
    session = await api.post(`/tracking/sessions/${session.id}/resume/`);
    syncedAt = Date.now();
    render();
  } catch (error) {
    toast.error(error.message || "Couldn't resume the session.");
  }
}

function promptEnd() {
  const dialog = document.getElementById("end-session-modal");
  if (!dialog) return;

  dialog.returnValue = "";
  dialog.showModal();

  dialog.addEventListener(
    "close",
    async () => {
      if (dialog.returnValue !== "confirm") return;

      const units = Number(document.getElementById("end-work-units").value);
      const pagesValue = document.getElementById("end-pages").value;

      try {
        // No end_time is sent. The server timestamps the close.
        await api.post(`/tracking/sessions/${session.id}/end/`, {
          work_units: units,
          review: document.getElementById("end-review").value || "",
          pages: pagesValue ? Number(pagesValue) : null,
        });
        session = null;
        render();
        toast.success("Work session recorded.");
      } catch (error) {
        toast.error(error.message || "Couldn't save that session.");
      }
    },
    { once: true },
  );
}
