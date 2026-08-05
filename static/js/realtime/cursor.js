/**
 * Per-topic replay cursors.
 *
 * The last outbox sequence seen on each topic. Sent on `resume` after a
 * reconnect so the server can replay exactly the gap — no duplicates, no
 * holes.
 *
 * Held in sessionStorage rather than memory so a page navigation inside the
 * app does not reset them and re-deliver events the user has already seen.
 */

const STORAGE_KEY = "opstracking:cursors";

function load() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function persist(state) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Private browsing or a full quota. Cursors degrade to memory-only,
    // which is correct-but-chatty rather than broken.
  }
}

let state = load();

export const cursors = {
  all() {
    return { ...state };
  },

  get(topic) {
    return state[topic] ?? 0;
  },

  /** Monotonic: an out-of-order frame must never rewind the cursor. */
  set(topic, seq) {
    if (!topic || !seq) return;
    if (seq > (state[topic] ?? 0)) {
      state[topic] = seq;
      persist(state);
    }
  },

  /** Adopt the server's view on connect, for topics we have not seen. */
  seed(serverCursors) {
    let changed = false;
    Object.entries(serverCursors || {}).forEach(([topic, seq]) => {
      if (state[topic] === undefined) {
        state[topic] = seq;
        changed = true;
      }
    });
    if (changed) persist(state);
  },

  clear() {
    state = {};
    persist(state);
  },
};
