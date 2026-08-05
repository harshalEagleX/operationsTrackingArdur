/**
 * A small shared store.
 *
 * Holds the bootstrap payload (the signed-in user, feature flags) and the
 * master-data caches every screen needs. Not a state management framework —
 * just one place for things that would otherwise be fetched four times per
 * page.
 */

import { api } from "./api.js";

function readBootstrap() {
  const element = document.getElementById("bootstrap-data");
  if (!element) return { user: null, features: {}, wsUrl: "", apiBase: "/api/v1" };
  try {
    return JSON.parse(element.textContent);
  } catch {
    console.error("bootstrap-data is not valid JSON");
    return { user: null, features: {}, wsUrl: "", apiBase: "/api/v1" };
  }
}

const bootstrap = readBootstrap();

export const store = {
  user: bootstrap.user,
  features: bootstrap.features || {},
  wsUrl: bootstrap.wsUrl || "",

  masters: null,
  presence: new Map(),
  unreadCount: 0,

  get isSupervisor() {
    return Boolean(this.user?.is_supervisor);
  },

  get isAdmin() {
    return Boolean(this.user?.is_admin);
  },

  get empId() {
    return this.user?.emp_id ?? null;
  },

  /** Fetch every dropdown list in one request. Cached for the page's life. */
  async loadMasters(force = false) {
    if (this.masters && !force) return this.masters;
    this.masters = await api.get("/masters/bundle/");
    return this.masters;
  },

  /** Fill a <select> from a master list. */
  fillSelect(select, items, { valueKey, labelKey, placeholder = "Select…" }) {
    if (!select) return;
    select.textContent = "";

    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = placeholder;
    select.appendChild(blank);

    items.forEach((item) => {
      const option = document.createElement("option");
      option.value = item[valueKey];
      option.textContent = item[labelKey];
      select.appendChild(option);
    });
  },
};
