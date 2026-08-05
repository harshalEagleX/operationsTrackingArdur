/**
 * Notification bell and centre.
 *
 * Loads the unread count once, then updates from `notification.created`
 * frames on the socket. Never polls — that was the whole point of building
 * the realtime layer.
 */

import { api } from "../core/api.js";
import { bus } from "../core/bus.js";
import { store } from "../core/store.js";
import { toast } from "../core/toast.js";

let oldestSeen = null;

export function initNotifications() {
  const bell = document.getElementById("bell-btn");
  const centre = document.getElementById("notification-center");
  if (!bell || !centre) return;

  bell.addEventListener("click", () => {
    const opening = centre.hidden;
    centre.hidden = !opening;
    bell.setAttribute("aria-expanded", String(opening));
    if (opening) loadNotifications({ reset: true });
  });

  document.addEventListener("click", (event) => {
    if (!centre.hidden && !centre.contains(event.target) && event.target !== bell) {
      centre.hidden = true;
      bell.setAttribute("aria-expanded", "false");
    }
  });

  document.getElementById("mark-all-read")?.addEventListener("click", markAllRead);
  document
    .getElementById("load-more-notifications")
    ?.addEventListener("click", () => loadNotifications({ reset: false }));

  // Live arrivals.
  bus.on("notification.created", (notification) => {
    store.unreadCount += 1;
    renderBadge();
    prependNotification(notification);

    toast.show(notification.title, {
      type: notification.priority === "critical" ? "error" : "info",
      action: notification.link_url
        ? { label: "View", onClick: () => (window.location.href = notification.link_url) }
        : null,
    });
  });

  bus.on("notification.read", (payload) => {
    store.unreadCount = payload.unread_count ?? 0;
    renderBadge();
  });

  loadUnreadCount();
}

async function loadUnreadCount() {
  try {
    const result = await api.get("/notifications/unread-count/");
    store.unreadCount = result.unread_count;
    renderBadge();
  } catch {
    // A missing badge is cosmetic; do not shout about it.
  }
}

async function loadNotifications({ reset }) {
  const list = document.getElementById("notification-list");
  const empty = document.getElementById("notifications-empty");
  if (!list) return;

  if (reset) {
    list.textContent = "";
    oldestSeen = null;
  }

  try {
    // Keyset, not page numbers — an inbox only grows.
    const items = await api.get("/notifications/", oldestSeen ? { before: oldestSeen } : {});
    const rows = Array.isArray(items) ? items : [];

    rows.forEach((notification) => list.appendChild(renderNotification(notification)));
    if (rows.length) oldestSeen = rows[rows.length - 1].id;

    if (empty) empty.hidden = list.children.length > 0;

    const loadMore = document.getElementById("load-more-notifications");
    if (loadMore) loadMore.hidden = rows.length === 0;
  } catch {
    toast.error("Couldn't load your notifications. Try again in a moment.");
  }
}

function renderNotification(notification) {
  const item = document.createElement("li");
  item.className = `nc-item${notification.is_read ? "" : " nc-unread"}`;
  item.dataset.id = notification.id;

  const title = document.createElement("p");
  title.className = "nc-title";
  title.textContent = notification.title;
  item.appendChild(title);

  if (notification.body) {
    const body = document.createElement("p");
    body.className = "nc-body";
    body.textContent = notification.body;
    item.appendChild(body);
  }

  const time = document.createElement("time");
  time.className = "nc-time";
  time.dateTime = notification.created_at;
  time.textContent = relativeTime(notification.created_at);
  item.appendChild(time);

  if (notification.link_url) {
    item.classList.add("nc-clickable");
    item.addEventListener("click", async () => {
      await api.post("/notifications/read/", { ids: [notification.id] });
      window.location.href = notification.link_url;
    });
  }

  return item;
}

function prependNotification(notification) {
  const list = document.getElementById("notification-list");
  if (list?.children.length) list.prepend(renderNotification(notification));
}

async function markAllRead() {
  try {
    await api.post("/notifications/read/", {});
    store.unreadCount = 0;
    renderBadge();
    document
      .querySelectorAll(".nc-item")
      .forEach((item) => item.classList.remove("nc-unread"));
  } catch {
    toast.error("Couldn't mark those as read.");
  }
}

function renderBadge() {
  const badge = document.getElementById("bell-badge");
  if (!badge) return;
  badge.textContent = store.unreadCount > 99 ? "99+" : String(store.unreadCount);
  badge.hidden = store.unreadCount === 0;
}

function relativeTime(iso) {
  const then = new Date(iso);
  const seconds = Math.round((Date.now() - then.getTime()) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return then.toLocaleDateString();
}
