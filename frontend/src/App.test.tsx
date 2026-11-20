import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import App from "./App";
import { FakeEventSource, aiOverview, fakeBackend, ollamaRunning } from "./test/fakeBackend";

test("shows the app frame and that the backend is connected", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1.2.3" },
    "GET /api/ai": aiOverview(),
  });
  render(<App />);
  expect(await screen.findByText("Backend connected")).toBeInTheDocument();
  expect(await screen.findByText("AI: Ollama · gemma4:12b")).toBeInTheDocument();
  expect(screen.queryByText("Version 1.2.3")).not.toBeInTheDocument(); // no version in the sidebar any more
});

test("the sidebar shows only the logo, and Ctrl+K or its Search button opens the command centre", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/library";
  fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1" },
    "GET /api/ai": aiOverview(),
    "GET /api/library/filters": {
      platforms: [], kinds: [], no_collection: 0,
      collections: [{ id: 3, label: "Cooking", count: 4 }],
      tags: [{ id: "dinner", label: "dinner", count: 2 }],
      creators: [{ id: "sam", label: "@sam", count: 5 }],
    },
  });
  render(<App />);
  await screen.findByText("Backend connected");
  expect(screen.queryByText("Keptwise")).not.toBeInTheDocument(); // just the logo
  expect(screen.queryByRole("searchbox", { name: "Search your saves" })).not.toBeInTheDocument(); // no search bar across the top

  fireEvent.click(screen.getByRole("button", { name: "Search and commands" }));
  const centre = await screen.findByRole("dialog", { name: "Command centre" });
  const box = within(centre).getByRole("combobox");
  expect(within(centre).getByRole("option", { name: /Go to Library/ })).toBeInTheDocument();

  // A prefix looks in one place: "/" is collections, Enter opens the first.
  fireEvent.change(box, { target: { value: "/coo" } });
  expect(await within(centre).findByRole("option", { name: /Cooking/ })).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(box, { key: "Enter" });
  expect(window.location.hash).toBe("#/collections/3");
  expect(screen.queryByRole("dialog", { name: "Command centre" })).not.toBeInTheDocument();

  act(() => {
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
  });
  const again = within(await screen.findByRole("dialog", { name: "Command centre" })).getByRole("combobox");
  fireEvent.change(again, { target: { value: "#din" } });
  fireEvent.keyDown(again, { key: "Enter" });
  expect(window.location.hash).toBe("#/library?tag=dinner");
});

test("first run shows the setup wizard, and Skip closes it", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1" },
    "GET /api/ai/ollama": ollamaRunning,
    "GET /api/ai": aiOverview({ setup_done: false }),
    "POST /api/ai/setup-done": aiOverview({ setup_done: true }),
  });
  render(<App />);
  expect(await screen.findByText("Welcome to Keptwise")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Free, on this PC"));
  expect(await screen.findByText(/Ollama 0.40.15 is running/)).toBeInTheDocument();

  fireEvent.click(screen.getByText("Skip for now"));
  await vi.waitFor(() => expect(screen.queryByText("Welcome to Keptwise")).not.toBeInTheDocument());
  expect(calls.some((c) => c.method === "POST" && c.url === "/api/ai/setup-done")).toBe(true);
});

test("the tutorial follows setup and can be replayed from Settings", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/library";
  const calls = fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1" },
    "GET /api/ui": { welcomed: false, tutorial_seen: false },
    "PUT /api/ui": (body: unknown) => body,
    "GET /api/ai": aiOverview({ setup_done: false }),
    "POST /api/ai/setup-done": aiOverview({ setup_done: true }),
  });
  render(<App />);
  const setup = await screen.findByRole("dialog", { name: "Set up Keptwise" });
  expect(screen.queryByRole("dialog", { name: "Keptwise tutorial" })).not.toBeInTheDocument();
  fireEvent.click(within(setup).getByRole("button", { name: "Skip" }));
  fireEvent.click(await screen.findByRole("button", { name: "Skip for now" }));

  const tour = await screen.findByRole("dialog", { name: "Keptwise tutorial" });
  expect(within(tour).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  fireEvent.click(within(tour).getByRole("button", { name: "Try sample import" }));
  expect(within(tour).getByText(/Two sample saves added/)).toBeInTheDocument();
  fireEvent.click(within(tour).getByRole("button", { name: "Next chapter" }));
  expect(within(tour).getByRole("heading", { name: "Try sorting a save" })).toHaveFocus();
  fireEvent.click(within(tour).getByRole("button", { name: "Get transcript" }));
  fireEvent.click(within(tour).getByRole("button", { name: "Write notes" }));
  fireEvent.change(within(tour).getByRole("combobox"), { target: { value: "Weeknight meals" } });
  fireEvent.click(within(tour).getByRole("button", { name: "Approve" }));
  expect(within(tour).getByText("Filed in Weeknight meals.")).toBeInTheDocument();

  fireEvent.click(within(tour).getByRole("button", { name: "Close tutorial" }));
  await vi.waitFor(() => expect(calls.some((c) => c.method === "PUT" && (c.body as { tutorial_seen?: boolean })?.tutorial_seen)).toBe(true));
  expect(screen.queryByRole("dialog", { name: "Keptwise tutorial" })).not.toBeInTheDocument();
  await act(async () => { window.location.hash = "#/settings?section=getting-started"; });
  fireEvent.click(await screen.findByRole("button", { name: "Open guided tutorial" }));

  const replay = await screen.findByRole("dialog", { name: "Keptwise tutorial" });
  expect(within(replay).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "1");
  fireEvent.click(within(replay).getByRole("button", { name: "Open Import" }));
  expect(window.location.hash).toBe("#/import");
  expect(screen.queryByRole("dialog", { name: "Keptwise tutorial" })).not.toBeInTheDocument();
});

test("an existing library can dismiss the new tutorial and keep its appearance", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1" },
    "GET /api/ui": { welcomed: true, tutorial_seen: false, name: "Sam", theme: "dark" },
    "PUT /api/ui": (body: unknown) => body,
    "GET /api/ai": aiOverview(),
  });
  render(<App />);
  const tour = await screen.findByRole("dialog", { name: "Keptwise tutorial" });
  fireEvent.keyDown(tour, { key: "Escape" });
  await vi.waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body)
    .toMatchObject({ tutorial_seen: true, welcomed: true, name: "Sam", theme: "dark" }));
  expect(screen.queryByRole("dialog", { name: "Keptwise tutorial" })).not.toBeInTheDocument();
});

test("explains when the backend can't be reached", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
  render(<App />);
  expect(await screen.findByText("Backend not reachable")).toBeInTheDocument();
});

test("a newer version: from source it links to GitHub, and Settings has the off switch", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const status = {
    enabled: true, current: "0.1.0", latest: "0.2.0", update_available: true, can_install: false,
    url: "https://github.com/x/releases/tag/v0.2.0", checked_at: "2026-11-11T10:00:00+00:00", error: null,
  };
  const calls = fakeBackend({
    "GET /api/hello": { message: "Hello", version: "0.1.0" },
    "GET /api/ai": aiOverview(),
    "GET /api/updates": status,
    "PUT /api/updates": { ...status, enabled: false },
  });
  window.location.hash = "#/settings";
  render(<App />);
  const links = await screen.findAllByRole("link", { name: "Get it from GitHub" });
  expect(links[0]).toHaveAttribute("href", "https://github.com/x/releases/tag/v0.2.0");
  expect(screen.queryByRole("button", { name: "Update now" })).not.toBeInTheDocument();
  fireEvent.click(await screen.findByLabelText(/Check for a new version once a day/));
  await vi.waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.url === "/api/updates")).toBe(true));
  window.location.hash = "";
});

test("in the installed app, Update now downloads and installs the new version", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/library";
  const status = {
    enabled: true, current: "1.0.0", latest: "1.1.0", update_available: true, can_install: true,
    url: "https://github.com/x/releases/tag/v1.1.0", checked_at: "2026-11-17T10:00:00+00:00", error: null,
  };
  const job = { id: 9, kind: "update", title: "Update Keptwise", status: "queued", progress: 0, total: 0, message: null, error: null, created_at: "", updated_at: "", finished_at: null, params: {}, result: null };
  const calls = fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1.0.0" },
    "GET /api/ai": aiOverview(),
    "GET /api/updates": status,
    "POST /api/updates/install": job,
  });
  render(<App />);
  expect(await screen.findByText("Version 1.1.0 is available")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Update now" }));
  await vi.waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/updates/install")).toBe(true));
});

test("a finished update from an earlier run doesn't show as installing", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/library";
  const status = {
    enabled: true, current: "1.0.0", latest: "1.1.0", update_available: true, can_install: true,
    url: "https://github.com/x/releases/tag/v1.1.0", checked_at: "2026-11-17T10:00:00+00:00", error: null,
  };
  const old = { id: 15, kind: "update", title: "Update Keptwise", status: "done", progress: 1, total: 1, message: "Installing version 1.0.0…", error: null, created_at: "", updated_at: "", finished_at: "", params: {}, result: { updated: true, version: "1.0.0" } };
  fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1.0.0" },
    "GET /api/ai": aiOverview(),
    "GET /api/updates": status,
    "GET /api/jobs": [old],
  });
  render(<App />);
  expect(await screen.findByRole("button", { name: "Update now" })).toBeInTheDocument();
  expect(screen.queryByText(/Installing version/)).not.toBeInTheDocument();
});

test("the sidebar has two sections, no Home, and the platform picker narrows to one platform", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const scope = (platform: string | null) => ({
    platform,
    total: 5,
    platforms: [{ id: "tiktok", label: "TikTok", count: 3 }, { id: "youtube", label: "YouTube", count: 2 }],
  });
  const calls = fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1" },
    "GET /api/ai/ready": { ready: false, message: "Ollama isn't running.", code: "unreachable" },
    "GET /api/ai": aiOverview(),
    "GET /api/scope": scope(null),
    "PUT /api/scope": scope("youtube"),
    "GET /api/overview": { counts: { review: 2, open_plans: 1, to_unsave: 0 }, recent: [] },
    "GET /api/library/filters": { platforms: [], kinds: [], collections: [], tags: [], creators: [], no_collection: 0 },
    "GET /api/library/items": { total: 0, offset: 0, items: [] },
  });
  window.location.hash = "#/library";
  render(<App />);
  const organise = await screen.findByRole("navigation", { name: "Organise" });
  expect(within(organise).getAllByRole("link").map((a) => a.textContent?.replace(/\d+$/, ""))).toEqual([
    "Library", "Collections", "Tags", "Plans", "AI Assistant", "Unsave", "Archive",
  ]);
  const manage = screen.getByRole("navigation", { name: "Manage" });
  expect(within(manage).getAllByRole("link").map((a) => a.textContent)).toEqual(["Import", "Sort", "Settings"]);
  expect(screen.queryByText("Home")).not.toBeInTheDocument();
  // The AI's state is checked too, not just its name.
  expect(await screen.findByText("Ollama isn't running.")).toBeInTheDocument();

  fireEvent.click(await screen.findByRole("button", { name: "Platform: All. Change" }));
  fireEvent.click(within(screen.getByRole("listbox", { name: "Platform" })).getByText("YouTube"));
  await vi.waitFor(() => expect(calls.find((c) => c.method === "PUT" && c.url === "/api/scope")?.body).toEqual({ platform: "youtube" }));
  expect(await screen.findByRole("button", { name: "Platform: YouTube. Change" })).toBeInTheDocument();
  window.location.hash = "";
});

test("the backend status is checked again later", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("EventSource", FakeEventSource);
  let up = true;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    if (!up) throw new TypeError("Failed to fetch");
    const data = url === "/api/ai" ? aiOverview() : url === "/api/hello" ? { message: "Hello", version: "1" } : null;
    if (data === null) return { ok: false, status: 404, json: async () => ({ detail: "Not found" }) };
    return { ok: true, status: 200, json: async () => data };
  }));
  try {
    render(<App />);
    expect(await screen.findByText("Backend connected")).toBeInTheDocument();
    up = false;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(16_000);
    });
    expect(await screen.findByText("Backend not reachable")).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test("setup and Settings share your automation choices", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/library";
  let settings = { auto_sort: false, auto_tag: false, auto_notes: false };
  const calls = fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1" },
    "GET /api/ai": aiOverview(),
    "GET /api/ui": { welcomed: false },
    "PUT /api/ui": (body: unknown) => body,
    "GET /api/sorting/settings": () => ({ settings, kinds: [] }),
    "PATCH /api/sorting/settings": (body: unknown) => {
      settings = { ...settings, ...(body as Partial<typeof settings>) };
      return { settings, kinds: [] };
    },
  });
  render(<App />);
  const setup = await screen.findByRole("dialog", { name: "Set up Keptwise" });
  fireEvent.click(within(setup).getByRole("button", { name: "Make it mine" }));
  fireEvent.click(within(setup).getByRole("button", { name: "Next" }));
  fireEvent.click(within(setup).getByRole("button", { name: "Next" }));
  const autoTag = await within(setup).findByRole("switch", { name: "Add tags automatically" });
  expect(autoTag).not.toBeChecked();
  fireEvent.click(autoTag);
  await vi.waitFor(() => expect(autoTag).toBeChecked());
  expect(calls.find((call) => call.method === "PATCH")?.body).toEqual({ auto_tag: true });
  fireEvent.click(within(setup).getByRole("button", { name: "Next" }));
  fireEvent.click(within(setup).getByRole("button", { name: "Look around first" }));

  await act(async () => { window.location.hash = "#/settings?section=workflow"; });
  const workflow = await screen.findByRole("region", { name: "Workflow" });
  expect(await within(workflow).findByRole("switch", { name: "Add tags automatically" })).toBeChecked();
  expect(within(workflow).getByRole("link", { name: "Choose where imports go" })).toHaveAttribute("href", "#/collections/links");
  const autoSort = within(workflow).getByRole("switch", { name: "Put into collections automatically" });
  fireEvent.click(autoSort);
  await vi.waitFor(() => expect(autoSort).toBeChecked());
  expect(settings).toEqual({ auto_sort: true, auto_tag: true, auto_notes: false });
});

test("the first time, a short setup makes the app yours, and Skip keeps the standard look", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/library";
  const calls = fakeBackend({
    "GET /api/hello": { message: "Hello", version: "1" },
    "GET /api/ai": aiOverview(),
    "GET /api/ui": { theme: "system", accent: "default", text_size: "normal", start_page: "library", name: "", welcomed: false },
    "PUT /api/ui": (body: unknown) => body,
  });
  render(<App />);
  const setup = await screen.findByRole("dialog", { name: "Set up Keptwise" });
  fireEvent.change(within(setup).getByPlaceholderText("Your name (optional)"), { target: { value: "Sam" } });
  fireEvent.click(within(setup).getByRole("button", { name: "Make it mine" }));
  expect(await within(setup).findByRole("heading", { name: "How should it look, Sam?" })).toBeInTheDocument();
  fireEvent.click(within(setup).getByRole("button", { name: "Accent colour: Default. Change" }));
  fireEvent.click(screen.getByRole("radio", { name: "Teal" }));
  fireEvent.click(within(setup).getByRole("button", { name: "Skip" }));
  await act(async () => undefined);
  expect(screen.queryByRole("dialog", { name: "Set up Keptwise" })).not.toBeInTheDocument();
  const saved = calls.filter((c) => c.method === "PUT" && c.url === "/api/ui").map((c) => c.body as Record<string, unknown>);
  expect(saved.at(-1)).toMatchObject({ name: "Sam", accent: "teal", welcomed: true });
});
