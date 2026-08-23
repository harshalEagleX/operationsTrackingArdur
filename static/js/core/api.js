/**
 * The fetch wrapper. Every request to /api/v1/ goes through here.
 *
 * Three things it centralises:
 *   - the CSRF header, which DRF SessionAuthentication requires on every
 *     unsafe method (without it every POST is a 403);
 *   - unwrapping the {ok, data, meta} success envelope;
 *   - turning the {ok:false, error:{code, message}} envelope into a thrown
 *     ApiError with a message written for a human.
 */

import { toast } from "./toast.js";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor({ code, message, details }, status) {
    super(message || "Something went wrong.");
    this.name = "ApiError";
    this.code = code || "error";
    this.details = details || {};
    this.status = status;
  }

  /** True when the server rejected specific fields, so a form can highlight them. */
  get isValidation() {
    return this.code === "validation_error";
  }
}

function getCsrfToken() {
  const match = document.cookie
    .split("; ")
    .find((c) => c.startsWith("csrftoken="));
  return match ? decodeURIComponent(match.split("=")[1]) : "";
}

async function handle(response) {
  // 204 has no body; parsing it throws.
  if (response.status === 204) return null;

  let payload;
  try {
    payload = await response.json();
  } catch {
    if (response.ok) return null;
    throw new ApiError(
      { code: "server_error", message: "The server sent an unreadable response." },
      response.status,
    );
  }

  if (!response.ok) {
    // A 401 anywhere means the session is gone. Redirect rather than
    // showing an error the user cannot act on.
    // However, do not redirect if we are already on the login page (e.g. failing to log in).
    if (response.status === 401) {
      if (window.location.pathname !== '/login/') {
        window.location.href = "/login/?reason=session_expired";
      }
      throw new ApiError(payload?.error || { code: "unauthenticated", message: "Invalid credentials or session expired." }, 401);
    }
    throw new ApiError(payload.error || {}, response.status);
  }

  // Unwrap the envelope but keep `meta` reachable for paginated callers.
  if (payload && typeof payload === "object" && "ok" in payload) {
    if (payload.meta !== undefined) {
      return Object.assign(payload.data ?? {}, { __meta: payload.meta });
    }
    return payload.data;
  }
  return payload;
}

async function request(method, path, { body, params, signal, raw = false } = {}) {
  const url = new URL(path.startsWith("http") ? path : BASE + path, window.location.origin);

  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== "") {
        url.searchParams.set(key, value);
      }
    });
  }

  const options = {
    method,
    credentials: "same-origin",
    headers: { Accept: "application/json" },
    signal,
  };

  if (body instanceof FormData) {
    // Do NOT set Content-Type — the browser must add the multipart boundary.
    options.body = body;
  } else if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    options.headers["X-CSRFToken"] = getCsrfToken();
  }

  const response = await fetch(url, options);
  return raw ? response : handle(response);
}

export const api = {
  get: (path, params, opts) => request("GET", path, { params, ...opts }),
  post: (path, body, opts) => request("POST", path, { body, ...opts }),
  put: (path, body, opts) => request("PUT", path, { body, ...opts }),
  patch: (path, body, opts) => request("PATCH", path, { body, ...opts }),
  delete: (path, opts) => request("DELETE", path, opts),

  /** Upload a file and return its StoredFile record. */
  async upload(file, context = "misc") {
    const form = new FormData();
    form.append("file", file);
    form.append("context", context);
    return request("POST", "/files/", { body: form });
  },
};

/**
 * Run an API call and show a toast if it fails.
 *
 * Use for fire-and-forget actions. When a form needs to highlight fields,
 * catch the ApiError yourself and read `.details` instead.
 */
export async function tryApi(promise, { onError } = {}) {
  try {
    return await promise;
  } catch (error) {
    if (error instanceof ApiError) {
      if (onError) onError(error);
      else toast.error(error.message);
    }
    throw error;
  }
}

export { getCsrfToken };
