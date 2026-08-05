/**
 * Exponential backoff with jitter.
 *
 * The jitter is the whole point. When the websocket process restarts, every
 * connected browser is disconnected in the same instant. Without jitter they
 * all wait exactly 2s, then exactly 4s, and arrive in lockstep — a thundering
 * herd that knocks the process over again on each attempt.
 */

const BASE_MS = 1000;
const MAX_MS = 30000;

let attemptFloor = 0;

/** Delay before attempt N, spread across [0.5x, 1.5x] of the backoff window. */
export function nextDelay(attempt) {
  const exponential = Math.min(BASE_MS * 2 ** Math.max(attempt - 1, 0), MAX_MS);
  const jittered = exponential * (0.5 + Math.random());
  return Math.round(Math.min(jittered, MAX_MS * 1.5));
}

export function resetBackoff() {
  attemptFloor = 0;
}

export function currentFloor() {
  return attemptFloor;
}
