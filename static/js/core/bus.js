/**
 * A tiny pub/sub.
 *
 * Realtime frames land here, and features subscribe by event type. That
 * indirection is what lets the transport change — websocket today, polling on
 * a constrained host — without touching a single feature module.
 */

const listeners = new Map();

export const bus = {
  /** Subscribe. Returns an unsubscribe function. */
  on(event, handler) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(handler);
    return () => this.off(event, handler);
  },

  /** Subscribe for exactly one delivery. */
  once(event, handler) {
    const wrapped = (payload) => {
      this.off(event, wrapped);
      handler(payload);
    };
    return this.on(event, wrapped);
  },

  off(event, handler) {
    listeners.get(event)?.delete(handler);
  },

  emit(event, payload) {
    // Copy before iterating: a handler that unsubscribes itself would
    // otherwise mutate the set mid-iteration.
    const handlers = listeners.get(event);
    if (handlers) {
      [...handlers].forEach((handler) => {
        try {
          handler(payload);
        } catch (error) {
          // One broken listener must not stop the others from running.
          console.error(`bus handler for "${event}" threw:`, error);
        }
      });
    }

    // Wildcard listeners see everything — used by the debug console.
    listeners.get("*")?.forEach((handler) => handler(event, payload));
  },

  clear(event) {
    if (event) listeners.delete(event);
    else listeners.clear();
  },
};
