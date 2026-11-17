import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { FakeEventSource, aiOverview, fakeBackend, makeJob, ollamaRunning } from "../../test/fakeBackend";
import type { AiOverview } from "./aiApi";
import AiSettings from "./AiSettings";

test("switching to Cloud picks Claude and shows the key box", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const cloud = aiOverview({ current: "anthropic", current_kind: "cloud", current_label: "Claude · claude-haiku-5-5" });
  const calls = fakeBackend({
    "GET /api/ai/ollama": ollamaRunning,
    "PUT /api/ai/current": cloud,
  });
  let latest = aiOverview() as AiOverview;
  const { rerender } = render(<AiSettings overview={latest} onChange={(o) => (latest = o)} />);

  fireEvent.click(screen.getByRole("radio", { name: "Cloud (your API key)" }));
  await vi.waitFor(() => expect(latest.current).toBe("anthropic"));
  expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ provider: "anthropic" });

  rerender(<AiSettings overview={latest} onChange={(o) => (latest = o)} />);
  expect(screen.getByText("Claude API key")).toBeInTheDocument();
  expect(screen.getByPlaceholderText("Paste your API key")).toHaveAttribute("type", "password");
});

test("downloading a model shows live progress", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend({
    "GET /api/ai/ollama": ollamaRunning,
    "POST /api/ai/ollama/pull": makeJob({ id: 9, kind: "ollama_pull", status: "queued", params: { model: "gemma4:12b" } }),
  });
  render(<AiSettings overview={aiOverview() as AiOverview} onChange={() => undefined} />);

  const downloadButtons = await screen.findAllByText("Download");
  fireEvent.click(downloadButtons[0]);
  await vi.waitFor(() => expect(calls.some((c) => c.url === "/api/ai/ollama/pull")).toBe(true));

  act(() =>
    FakeEventSource.last?.emit(
      "job",
      makeJob({
        id: 9, kind: "ollama_pull", status: "running", progress: 4e9, total: 8e9,
        message: "Downloading gemma4:12b: 4.0 of 8.0 GB", params: { model: "gemma4:12b" },
      }),
    ),
  );
  expect(await screen.findByText("Downloading gemma4:12b: 4.0 of 8.0 GB")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Downloading gemma4:12b" })).toHaveAttribute("aria-valuenow", "50");
});

test("a download cut off by a restart offers Resume", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  fakeBackend({
    "GET /api/ai/ollama": ollamaRunning,
    "GET /api/jobs": [makeJob({ id: 3, kind: "ollama_pull", status: "interrupted", params: { model: "gemma4:12b" } })],
  });
  render(<AiSettings overview={aiOverview() as AiOverview} onChange={() => undefined} />);
  expect(await screen.findByRole("button", { name: "Resume download" })).toBeInTheDocument();
});

test("a model that can't fit on the disk can't be downloaded", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  // 7 GB free is too little for the 8 GB model (the app keeps a 10% safety margin).
  fakeBackend({ "GET /api/ai/ollama": { ...ollamaRunning, free_bytes: 7e9 } });
  render(<AiSettings overview={aiOverview() as AiOverview} onChange={() => undefined} />);
  const buttons = await screen.findAllByRole("button", { name: "Download" });
  expect(buttons[0]).toBeDisabled(); // gemma4:12b
  expect(screen.getAllByText(/Not enough free disk space/).length).toBeGreaterThan(0);
});

test("when Ollama isn't running it explains how to install it", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  fakeBackend({ "GET /api/ai/ollama": { ...ollamaRunning, running: false, version: null } });
  render(<AiSettings overview={aiOverview() as AiOverview} onChange={() => undefined} />);
  expect(await screen.findByText("Ollama isn't running on this PC.")).toBeInTheDocument();
  expect(screen.getByText("ollama.com/download")).toHaveAttribute("href", "https://ollama.com/download");
  expect(screen.getByText("Check again")).toBeInTheDocument();
});
