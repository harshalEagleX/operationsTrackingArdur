/**
 * Break buttons and countdown.
 *
 * Allowances come from /api/v1/breaks/types/ and are displayed only. The
 * client never sends an allowance — the server owns that number, which is why
 * you cannot give yourself a four-hour tea break from devtools.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { toast } from "../core/toast.js";

let current = null;
let syncedAt = 0;
let ticker = null;

export async function initBreaks() {
  document.getElementById("end-break-btn")?.addEventListener("click", endBreak);

  bus.on("break.started", refresh);
  bus.on("break.ended", refresh);

  await Promise.all([renderButtons(), refresh()]);
}

async function renderButtons() {
  const container = document.getElementById("break-buttons");
  if (!container) return;

  try {
    const types = await api.get("/breaks/types/");
    container.textContent = "";

    (types || []).forEach((type) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn break-btn";
      button.textContent = `${type.break_type} (${type.allotted_minutes}m)`;
      button.disabled = type.taken_today;
      if (type.taken_today) button.title = "Already taken today";
      button.addEventListener("click", () => startBreak(type.break_type));
      container.appendChild(button);
    });
  } catch {
    toast.error("Couldn't load the break types.");
  }
}

async function refresh() {
  try {
    current = await api.get("/breaks/current/");
    syncedAt = Date.now();
    render();
  } catch {
    // keep the last known state
  }
}

function render() {
  const panel = document.getElementById("break-running");
  const buttons = document.getElementById("break-buttons");
  if (!panel || !buttons) return;

  panel.hidden = !current;
  buttons.hidden = Boolean(current);

  if (!current) {
    stopTicker();
    renderButtons();
    return;
  }

  document.getElementById("break-meta").textContent =
    `${current.break_type} · ${Math.round((current.allotted_time || 0) / 60)} minutes allowed`;

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
  const display = document.getElementById("break-timer");
  if (!display || !current) return;

  const drift = (Date.now() - syncedAt) / 1000;
  const remaining = current.remaining_seconds - drift;

  const overrun = remaining < 0;
  const value = Math.floor(Math.abs(remaining));
  const minutes = String(Math.floor(value / 60)).padStart(2, "0");
  const seconds = String(value % 60).padStart(2, "0");

  display.textContent = `${overrun ? "+" : ""}${minutes}:${seconds}`;
  display.classList.toggle("timer-overrun", overrun);
}

async function startBreak(breakType) {
  try {
    current = await api.post("/breaks/", { break_type: breakType });
    syncedAt = Date.now();
    render();
  } catch (error) {
    toast.error(error.message || "Couldn't start that break.");
  }
}

async function endBreak() {
  try {
    const finished = await api.post("/breaks/end/", {});
    current = null;
    render();

    if (finished.is_overrun) {
      toast.warning(
        `Break ended — you were over your allowance by ${Math.round(finished.total_time / 60 - finished.allotted_time / 60)} minutes.`,
      );
    } else {
      toast.success("Break ended.");
    }
  } catch (error) {
    toast.error(error.message || "Couldn't end that break.");
  }
}
