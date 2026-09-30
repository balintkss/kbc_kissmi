// The bearer token intentionally stays only in this module's memory.
// Do not move it to localStorage, a URL, a cookie or a Vite environment variable.
let accessToken = null;

export class ApiError extends Error {
  constructor(status) {
    super(`Request failed (${status})`);
    this.status = status;
  }
}

export function setAccessToken(token) {
  accessToken = token || null;
}

export function clearAccessToken() {
  accessToken = null;
}

export async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const response = await fetch(`/api${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    credentials: "omit",
    cache: "no-store",
    referrerPolicy: "no-referrer",
  });

  if (response.status === 401 && path !== "/auth/login") {
    clearAccessToken();
    window.dispatchEvent(new Event("twin:session-ended"));
  }
  if (!response.ok) throw new ApiError(response.status);
  return response.json();
}

export function friendlyError(error, context = "load this") {
  if (!(error instanceof ApiError)) return `We could not ${context}. Check that the local API is running.`;
  if (error.status === 401) return "Your session ended. Please sign in again.";
  if (error.status === 404) return "That item is not available right now.";
  if (error.status === 422) return "That request was not valid. Please check the information and try again.";
  if (error.status === 429) return "Please slow down for a moment, then try again.";
  if (error.status === 503) return "Kate is unavailable right now. You can try again shortly.";
  return `We could not ${context}. Please try again.`;
}
