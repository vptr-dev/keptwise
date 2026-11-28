import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { FakeEventSource, fakeBackend, makeJob } from "../test/fakeBackend";
import ImportPage from "./ImportPage";

const summary = (tiktok: number) => ({
  total: tiktok,
  platforms: [
    { platform: "tiktok", name: "TikTok", count: tiktok },
    { platform: "youtube", name: "YouTube", count: 0 },
    { platform: "instagram", name: "Instagram", count: 0 },
    { platform: "facebook", name: "Facebook", count: 0 },
  ],
});

/** Stands in for XMLHttpRequest: every upload succeeds at once. */
class FakeXhr {
  static sent: { url: string; body: unknown }[] = [];
  upload: { onprogress: ((event: { loaded: number }) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  status = 0;
  responseText = "{}";
  private url = "";
  open(_method: string, url: string) {
    this.url = url;
  }
  send(body: File) {
    FakeXhr.sent.push({ url: this.url, body });
    setTimeout(() => {
      this.upload.onprogress?.({ loaded: body.size });
      this.status = 200;
      this.onload?.();
    });
  }
  abort() {
    this.onabort?.();
  }
}

test("paste a video link and refresh the library count after adding it", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  let count = 0;
  const calls = fakeBackend({
    "GET /api/jobs": [],
    "GET /api/imports/summary": () => summary(count),
    "POST /api/imports/link": () => {
      count++;
      return {status: "added", platform_name: "TikTok"};
    },
  });
  render(<ImportPage />);
  const input = screen.getByRole("textbox", {name: "Video link"});
  const url = "https://vm.tiktok.com/sample/";
  fireEvent.change(input, {target: {value: url}});
  fireEvent.click(screen.getByRole("button", {name: "Add to Library"}));
  expect(await screen.findByText(/TikTok save added/)).toBeInTheDocument();
  expect(calls.find(c => c.url === "/api/imports/link")?.body).toEqual({url});
  expect(input).toHaveValue("");
  expect(await screen.findByTestId("count-tiktok")).toHaveTextContent("1");
});

const importJob = (overrides: Record<string, unknown>) =>
  makeJob({ id: 4, kind: "import", title: "Import tiktok.zip", status: "queued", ...overrides });

test("choosing a zip copies it, imports it and shows what was found", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  FakeXhr.sent = [];
  let count = 0;
  const calls = fakeBackend({
    "GET /api/imports/summary": () => summary(count),
    "GET /api/jobs": [],
    "POST /api/imports/abc/start": importJob({}),
    "POST /api/imports": { upload_id: "abc", wanted_names: [], wanted_extensions: [".zip"] },
  });

  render(<ImportPage />);
  expect(await screen.findByTestId("count-tiktok")).toHaveTextContent("0");
  expect(screen.getByText("How to get your export")).toBeInTheDocument();

  const zip = new File(["fake zip bytes"], "tiktok.zip", { type: "application/zip" });
  fireEvent.change(screen.getByLabelText("Export file"), { target: { files: [zip] } });

  expect(await screen.findByText("Import tiktok.zip")).toBeInTheDocument();
  expect(FakeXhr.sent).toEqual([{ url: "/api/imports/abc/files?path=tiktok.zip", body: zip }]);
  expect(calls.find((c) => c.url === "/api/imports/abc/start")?.body).toEqual({ name: "tiktok.zip" });

  act(() => FakeEventSource.last?.emit("job", importJob({ status: "running", progress: 2, total: 3, message: "Saved 2 of 3" })));
  expect(await screen.findByText("Saved 2 of 3")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Import tiktok.zip" })).toHaveAttribute("aria-valuenow", "67");

  count = 3;
  const result = {
    message: "Imported 3 new saves from TikTok.",
    found: 3,
    new: 3,
    already_had: 0,
    platforms: [
      {
        platform: "tiktok",
        name: "TikTok",
        found: 3,
        new: 3,
        already_had: 0,
        collections: ["Recipes"],
        notes: ["Skipped 2 liked videos: likes aren't saves."],
      },
    ],
  };
  act(() =>
    FakeEventSource.last?.emit("job", importJob({ status: "done", progress: 3, total: 3, message: result.message, result })),
  );
  expect(await screen.findByText("Import finished")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Import collections" })).toHaveAttribute("href", "#/collections/links");
  expect(screen.getByText("Imported 3 new saves from TikTok.")).toBeInTheDocument();
  expect(screen.getByText("3 new")).toBeInTheDocument();
  expect(screen.getByText("Skipped 2 liked videos: likes aren't saves.")).toBeInTheDocument();
  // The library numbers refresh when the import finishes.
  expect(await screen.findByTestId("count-tiktok")).toHaveTextContent("3");
});

test("a folder with nothing importable says so and copies nothing", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("XMLHttpRequest", FakeXhr);
  FakeXhr.sent = [];
  fakeBackend({
    "GET /api/imports/summary": summary(0),
    "GET /api/jobs": [],
    "POST /api/imports": { upload_id: "abc", wanted_names: ["saved_posts.json"], wanted_extensions: [".zip"] },
    "DELETE /api/imports/abc": {},
  });

  render(<ImportPage />);
  const photo = new File(["x"], "photo.jpg");
  Object.defineProperty(photo, "webkitRelativePath", { value: "holiday/photo.jpg" });
  fireEvent.change(screen.getByLabelText("Export folder"), { target: { files: [photo] } });

  expect(await screen.findByText(/None of these files look like/)).toBeInTheDocument();
  expect(FakeXhr.sent).toEqual([]);
});

test("a failed import shows the reason", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  fakeBackend({
    "GET /api/imports/summary": summary(0),
    "GET /api/jobs": [importJob({ status: "running" })],
  });
  render(<ImportPage />);
  expect(await screen.findByRole("progressbar", { name: "Import tiktok.zip" })).toBeInTheDocument();
  act(() =>
    FakeEventSource.last?.emit("job", importJob({ status: "failed", error: "Couldn't find saved items in these files." })),
  );
  expect(await screen.findByText("The import didn't work")).toBeInTheDocument();
  expect(screen.getByText("Couldn't find saved items in these files.")).toBeInTheDocument();
});
