// Test helpers: a fake backend for fetch() and a fake live-update stream.
import { vi } from "vitest";

type Handler = (body: unknown, url: string) => unknown;

/** Return this from a route to answer with an error, e.g. httpError(409, { detail, code }). */
export class FakeHttpError {
  constructor(public status: number, public body: unknown) {}
}
export const httpError = (status: number, body: unknown) => new FakeHttpError(status, body);

/**
 * Routes look like "GET /api/ai" or "PUT /api/ai/current". The longest
 * matching prefix wins. Returns the list of calls made, for checking.
 */
export function fakeBackend(routes: Record<string, unknown | Handler>) {
  const calls: { method: string; url: string; body: unknown }[] = [];
  const keys = Object.keys(routes).sort((a, b) => b.length - a.length);
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : init?.body;
    calls.push({ method, url, body });
    const key = keys.find((k) => {
      const [m, path] = k.split(" ");
      return m === method && url.startsWith(path);
    });
    if (!key) return { ok: false, status: 404, json: async () => ({ detail: `No fake for ${method} ${url}` }) };
    const route = routes[key];
    const data = typeof route === "function" ? (route as Handler)(body, url) : route;
    if (data instanceof FakeHttpError) return { ok: false, status: data.status, json: async () => data.body };
    return { ok: true, status: 200, json: async () => data };
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export class FakeEventSource {
  static last: FakeEventSource | null = null;
  handlers: Record<string, ((event: MessageEvent<string>) => void)[]> = {};
  constructor(public url: string) {
    FakeEventSource.last = this;
  }
  addEventListener(type: string, handler: (event: MessageEvent<string>) => void) {
    (this.handlers[type] ??= []).push(handler);
  }
  emit(type: string, data: unknown) {
    for (const handler of this.handlers[type] ?? []) {
      handler({ data: JSON.stringify(data) } as MessageEvent<string>);
    }
  }
}

export function makeJob(overrides: Record<string, unknown>) {
  return {
    id: 1, kind: "demo", title: "Job", status: "running", progress: 0, total: 0,
    message: null, error: null, params: {}, result: null, created_at: "", finished_at: null,
    ...overrides,
  };
}

export function aiOverview(overrides: Record<string, unknown> = {}) {
  const provider = (id: string, label: string, kind: string, needs_key: boolean, model = "") => ({
    id, label, kind, needs_key, key_saved: false, key_hint: null, key_url: "",
    model, base_url: "", default_base_url: "",
  });
  return {
    current: "ollama",
    current_kind: "local",
    current_label: "Ollama · gemma4:12b",
    setup_done: true,
    providers: [
      provider("ollama", "Ollama", "local", false, "gemma4:12b"),
      provider("lmstudio", "LM Studio", "local", false),
      provider("anthropic", "Claude", "cloud", true, "claude-haiku-5-5"),
      provider("openai", "OpenAI", "cloud", true),
    ],
    ...overrides,
  };
}

export const ollamaRunning = {
  base_url: "http://localhost:11434",
  running: true,
  version: "0.40.15",
  installed: [],
  error: null,
  download_page: "https://ollama.com/download",
  default_model: "gemma4:12b",
  free_bytes: 50e9,
  recommended: [
    { name: "gemma4:12b", label: "Gemma 4 12B", size_gb: 8, note: "Recommended.", installed: false },
    { name: "gemma4:e4b", label: "Gemma 4 E4B", size_gb: 6.6, note: "Lighter.", installed: false },
  ],
};
