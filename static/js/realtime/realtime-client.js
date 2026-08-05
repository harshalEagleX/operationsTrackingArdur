/**
 * The socket. One per tab.
 *
 * Four details here are easy to skip and expensive to skip:
 *
 *  1. Jitter on backoff. If the server restarts, every browser reconnects.
 *     Without jitter they all arrive inside the same 50 ms and knock the
 *     websocket process over on its first breath.
 *
 *  2. Ping/pong with a deadline. A TCP connection can be dead while
 *     readyState still reads OPEN — mobile networks and captive portals do
 *     this routinely. Only an unanswered ping detects it.
 *
 *  3. Cursors and `resume`. On reconnect we tell the server the last sequence
 *     we saw per topic and it replays the gap. This is what makes a
 *     30-second tunnel invisible to the user.
 *
 *  4. The `pending` queue. A subscription sent while offline must survive;
 *     a typing indicator must not.
 */

import { bus } from "../core/bus.js";
import { cursors } from "./cursor.js";
import { nextDelay, resetBackoff } from "./reconnect.js";

const HEARTBEAT_MS = 20000;
const PONG_GRACE_MS = 10000;
const CLOSE_UNAUTHENTICATED = 4401;

export class RealtimeClient {
  constructor({ ticketUrl = "/api/v1/realtime/ticket/" } = {}) {
    this.ticketUrl = ticketUrl;
    this.ws = null;
    this.state = "idle";
    this.pending = [];
    this.heartbeatTimer = null;
    this.pongDeadline = null;
    this.attempt = 0;
  }

  async connect() {
    if (this.state === "connecting" || this.state === "open") return;
    this.state = "connecting";

    let ticket;
    let wsUrl;
    try {
      const response = await fetch(this.ticketUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": this.#csrf() },
      });

      if (response.status === 401) return this.#sessionExpired();
      if (!response.ok) throw new Error(`ticket request failed: ${response.status}`);

      const payload = await response.json();
      ticket = payload.data.ticket;
      wsUrl = payload.data.ws_url;
    } catch {
      // The API is unreachable. Back off and keep trying — this is a blip,
      // not a signed-out session.
      this.state = "closed";
      return this.#scheduleReconnect();
    }

    this.ws = new WebSocket(`${wsUrl}?ticket=${encodeURIComponent(ticket)}`);

    this.ws.onopen = () => {
      this.state = "open";
      this.attempt = 0;
      resetBackoff();

      // Ask for anything we missed before replaying our own queue.
      this.#send({ v: 1, op: "resume", data: { cursors: cursors.all() } });
      this.pending.splice(0).forEach((frame) => this.#send(frame));

      this.#startHeartbeat();
      bus.emit("realtime:open");
    };

    this.ws.onmessage = (event) => {
      let frame;
      try {
        frame = JSON.parse(event.data);
      } catch {
        return;
      }

      if (frame.op === "pong") {
        this.pongDeadline = null;
        return;
      }
      if (frame.op === "ready") {
        cursors.seed(frame.data.cursors || {});
        bus.emit("realtime:ready", frame.data);
        return;
      }
      if (frame.op === "error") {
        console.warn("realtime error:", frame.data);
        return;
      }
      if (frame.op === "ack") {
        bus.emit("realtime:ack", frame);
        return;
      }

      if (frame.seq && frame.topic) cursors.set(frame.topic, frame.seq);

      // Features subscribe by event type, never to the socket directly.
      bus.emit(frame.type, frame.data);
      bus.emit("realtime:event", frame);
    };

    this.ws.onclose = (event) => {
      this.state = "closed";
      this.#stopHeartbeat();
      bus.emit("realtime:closed", { code: event.code });

      // 4401 means the session is gone. Reconnecting would loop forever
      // against an endpoint that will never accept us.
      if (event.code === CLOSE_UNAUTHENTICATED) return this.#sessionExpired();

      this.#scheduleReconnect();
    };

    this.ws.onerror = () => this.ws?.close();
  }

  /** Queue a frame if the socket is down, send it if it is up. */
  send(frame, { queueIfOffline = true } = {}) {
    if (this.state === "open") this.#send(frame);
    else if (queueIfOffline) this.pending.push(frame);
  }

  subscribe(topic) {
    this.send({ v: 1, op: "sub", data: { topic } });
  }

  unsubscribe(topic) {
    this.send({ v: 1, op: "unsub", data: { topic } }, { queueIfOffline: false });
  }

  setPresence(status, customStatus = "") {
    this.send(
      { v: 1, op: "presence.set", data: { status, custom_status: customStatus } },
      { queueIfOffline: false },
    );
  }

  close() {
    this.#stopHeartbeat();
    this.state = "idle";
    this.ws?.close(1000, "client closing");
  }

  // ── internals ────────────────────────────────────────────

  #send(frame) {
    try {
      this.ws.send(JSON.stringify(frame));
    } catch (error) {
      console.warn("could not send frame", error);
    }
  }

  #csrf() {
    const match = document.cookie.split("; ").find((c) => c.startsWith("csrftoken="));
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }

  #startHeartbeat() {
    this.heartbeatTimer = setInterval(() => {
      if (this.pongDeadline && Date.now() > this.pongDeadline) {
        // A zombie socket: OPEN according to readyState, dead in fact.
        this.ws.close();
        return;
      }
      this.pongDeadline = Date.now() + PONG_GRACE_MS;
      this.#send({ v: 1, op: "ping" });
    }, HEARTBEAT_MS);
  }

  #stopHeartbeat() {
    if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
    this.heartbeatTimer = null;
    this.pongDeadline = null;
  }

  #scheduleReconnect() {
    this.attempt += 1;
    const delay = nextDelay(this.attempt);
    bus.emit("realtime:reconnecting", { attempt: this.attempt, delay });
    setTimeout(() => this.connect(), delay);
  }

  #sessionExpired() {
    this.state = "expired";
    this.#stopHeartbeat();
    bus.emit("realtime:expired");
    window.location.href = "/login/?reason=session_expired";
  }
}

export const realtime = new RealtimeClient();
