/**
 * Settings page — application settings, notification preferences, password.
 */

import { ApiError, api } from "../core/api.js";
import { store } from "../core/store.js";
import { toast } from "../core/toast.js";

document.addEventListener("DOMContentLoaded", async () => {
  await Promise.all([loadSettings(), loadPreferences()]);
  initPasswordForm();
});

async function loadSettings() {
  const container = document.getElementById("settings-list");
  if (!container) return;

  try {
    const settings = await api.get("/settings/");
    container.textContent = "";

    (Array.isArray(settings) ? settings : []).forEach((setting) => {
      const row = document.createElement("div");
      row.className = "setting-row";

      const label = document.createElement("label");
      label.className = "field";

      const name = document.createElement("span");
      name.className = "field-label";
      name.textContent = setting.label || setting.key;
      label.appendChild(name);

      const input = document.createElement("input");
      input.type = setting.value_type === "integer" ? "number" : "text";
      input.value = setting.value;
      input.disabled = !setting.is_editable || !store.isAdmin;
      input.addEventListener("change", () => save(setting.key, input.value));
      label.appendChild(input);

      row.appendChild(label);

      if (setting.description) {
        const hint = document.createElement("p");
        hint.className = "hint";
        hint.textContent = setting.description;
        row.appendChild(hint);
      }

      container.appendChild(row);
    });
  } catch (error) {
    toast.error(error.message || "Couldn't load the settings.");
  }
}

async function save(key, value) {
  try {
    await api.post("/settings/set/", { key, value });
    toast.success("Saved.");
  } catch (error) {
    toast.error(error.message || "Couldn't save that setting.");
  }
}

async function loadPreferences() {
  const table = document.getElementById("notification-prefs");
  if (!table) return;

  const body = table.querySelector("tbody");

  try {
    const preferences = await api.get("/notifications/preferences/");
    body.textContent = "";

    (Array.isArray(preferences) ? preferences : []).forEach((preference) => {
      const tr = document.createElement("tr");

      const name = document.createElement("td");
      name.textContent = preference.description || preference.notif_type;
      tr.appendChild(name);

      ["in_app", "email"].forEach((channel) => {
        const td = document.createElement("td");
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = preference[channel];
        checkbox.addEventListener("change", () =>
          savePreference(preference.notif_type, tr),
        );
        checkbox.dataset.channel = channel;
        td.appendChild(checkbox);
        tr.appendChild(td);
      });

      body.appendChild(tr);
    });
  } catch (error) {
    toast.error(error.message || "Couldn't load your notification preferences.");
  }
}

async function savePreference(notifType, row) {
  const boxes = row.querySelectorAll("input[type=checkbox]");
  try {
    await api.post("/notifications/preferences/", {
      notif_type: notifType,
      in_app: boxes[0].checked,
      email: boxes[1].checked,
    });
    toast.success("Preference saved.");
  } catch (error) {
    toast.error(error.message || "Couldn't save that preference.");
  }
}

function initPasswordForm() {
  const form = document.getElementById("password-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);

    try {
      await api.post("/auth/password/change/", {
        current_password: data.get("current_password"),
        new_password: data.get("new_password"),
        confirm_password: data.get("confirm_password"),
      });
      form.reset();
      toast.success("Your password has been changed.");
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Couldn't change your password.",
      );
    }
  });
}
