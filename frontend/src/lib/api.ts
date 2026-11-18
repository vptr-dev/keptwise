// Small helpers for calling the backend. The window sends the session
// cookie automatically, so no token handling is needed here.

export class ApiError extends Error {
  status: number;
  code: string | null; // e.g. "no_space", so the UI can offer the right fix
  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  if (signal) init.signal = signal;
  const response = await fetch(path, method === "GET" && !signal ? undefined : init);
  if (!response.ok) {
    let message = `The app's engine answered with status ${response.status}.`;
    let code: string | null = null;
    try {
      const data = (await response.json()) as { detail?: unknown; code?: unknown };
      if (typeof data.detail === "string") message = data.detail;
      if (typeof data.code === "string") code = data.code;
    } catch {
      // not JSON; keep the generic message
    }
    throw new ApiError(response.status, message, code);
  }
  if (method !== "GET") window.dispatchEvent(new Event(CHANGED)); // e.g. the Undo button looks again
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const CHANGED = "kw-data-changed";

/** Called after every change sent to the backend. */
export function onDataChange(listener: () => void): () => void {
  window.addEventListener(CHANGED, listener);
  return () => window.removeEventListener(CHANGED, listener);
}

export const api = {
  // signal: lets a search that's no longer wanted be cancelled.
  get: <T>(path: string, signal?: AbortSignal) => request<T>("GET", path, undefined, signal),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) => request<T>("POST", path, body, signal),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.code : null;
}
