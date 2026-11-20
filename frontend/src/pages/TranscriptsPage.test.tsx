import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import SpeechSettings from "../features/enrich/SpeechSettings";
import { FakeEventSource, fakeBackend, httpError, makeJob } from "../test/fakeBackend";
import TranscriptsPage from "./TranscriptsPage";

const speech = {
  model: "small",
  device: "auto",
  models: [
    { id: "base", label: "Base", approx_bytes: 145e6, hint: "Fast.", downloaded: false },
    { id: "small", label: "Small (recommended)", approx_bytes: 484e6, hint: "Good balance.", downloaded: true },
  ],
};

const overview = (counts: Partial<Record<string, number>> = {}) => ({
  counts: { total: 1995, waiting: 1995, done: 0, failed: 0, no_speech: 0, ...counts },
  speech,
});

const video = (overrides: Record<string, unknown>) => ({
  id: 1, platform: "tiktok", platform_name: "TikTok", url: "https://www.tiktokv.com/share/video/1/",
  title: "Easy pasta", author: "pasta.chef", duration_s: 46, seconds: 9.8, status: "enriched",
  error: null, has_thumbnail: true, transcript_preview: "Boil the water first, then add salt",
  transcript_chars: 837, no_speech: false, language: "en", ...overrides,
});

const enrichJob = (overrides: Record<string, unknown>) =>
  makeJob({ id: 7, kind: "enrich", title: "Transcripts for 5 videos", status: "queued", total: 5, ...overrides });

test("starting the next 5 shows live progress, pause, and the summary", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend({
    "GET /api/enrich/recent": [],
    "GET /api/enrich": overview(),
    "GET /api/jobs": [],
    "POST /api/enrich/start": enrichJob({}),
    "POST /api/jobs/7/pause": enrichJob({ status: "paused" }),
  });

  render(<TranscriptsPage />);
  expect(await screen.findByTestId("count-waiting")).toHaveTextContent("1,995");
  expect(screen.getByText(/Speech model: Small \(recommended\)/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Next 5" }));
  await waitFor(() => expect(calls.some((c) => c.url === "/api/enrich/start")).toBe(true));
  expect(calls.find((c) => c.url === "/api/enrich/start")?.body).toEqual({ count: 5, which: "waiting" });

  act(() => {
    FakeEventSource.last?.emit("job", enrichJob({ status: "running", progress: 2, message: "Transcribing video 3 of 5…" }));
  });
  expect(await screen.findByText("Transcribing video 3 of 5…")).toBeInTheDocument();
  expect(screen.getByText("2 / 5")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Transcripts for 5 videos" })).toHaveAttribute("aria-valuenow", "40");
  // Starting another batch waits until this one is finished.
  expect(screen.getByRole("button", { name: "Next 50" })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Pause" }));
  await waitFor(() => expect(calls.some((c) => c.url === "/api/jobs/7/pause")).toBe(true));
  act(() => {
    FakeEventSource.last?.emit("job", enrichJob({ status: "paused", progress: 2 }));
  });
  expect(await screen.findByRole("button", { name: "Resume" })).toBeInTheDocument();

  act(() => {
    FakeEventSource.last?.emit(
      "job",
      enrichJob({
        status: "done", progress: 5, message: "Finished 5 videos: 3 transcribed, 2 with no speech.",
        result: { device: "cpu", model: "small" },
      }),
    );
  });
  expect(await screen.findByText("Finished 5 videos: 3 transcribed, 2 with no speech.")).toBeInTheDocument();
  expect(screen.getByText(/running on the processor/)).toBeInTheDocument();
});

test("recent videos show the transcript, no speech, or why it failed", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  fakeBackend({
    "GET /api/enrich/recent": [
      video({}),
      video({ id: 2, title: "Goals", author: "goal.clips", duration_s: 30, seconds: 5.9, no_speech: true, transcript_preview: null, transcript_chars: 0 }),
      video({ id: 3, title: null, author: null, seconds: 0.7, status: "failed", error: "This video is private, so only the person who posted it can see it.", has_thumbnail: false, transcript_preview: null, transcript_chars: null }),
    ],
    "GET /api/enrich": overview({ waiting: 1992, done: 2, failed: 1, no_speech: 1 }),
    "GET /api/jobs": [],
  });

  render(<TranscriptsPage />);
  expect(await screen.findByText("Recently done")).toBeInTheDocument();
  expect(screen.getByText(/Boil the water first, then add salt/)).toBeInTheDocument();
  expect(screen.getByText("took 9.8 s")).toBeInTheDocument();
  expect(screen.getByText("TikTok · @pasta.chef · 0:46")).toBeInTheDocument();
  expect(screen.getByText("The speech model didn't detect any words.")).toBeInTheDocument();
  expect(screen.getByText(/This video is private/)).toBeInTheDocument();
  expect(screen.getAllByText("Couldn't read")).toHaveLength(2); // the count and the badge
  expect(screen.getByRole("button", { name: "Try the 1 failed again" })).toBeInTheDocument();
});

test("with nothing imported it points to the Import screen", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  fakeBackend({
    "GET /api/enrich/recent": [],
    "GET /api/enrich": overview({ total: 0, waiting: 0 }),
    "GET /api/jobs": [],
  });
  render(<TranscriptsPage />);
  expect(await screen.findByRole("button", { name: "Import your saves" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Next/ })).not.toBeInTheDocument();
});

test("the speech settings save the chosen model", async () => {
  const calls = fakeBackend({
    "GET /api/enrich": overview(),
    "PUT /api/enrich/settings": { ...speech, model: "base" },
  });
  render(<SpeechSettings />);
  const select = await screen.findByLabelText("Speech model");
  expect(select).toHaveValue("small");
  fireEvent.change(select, { target: { value: "base" } });
  await waitFor(() => expect(select).toHaveValue("base"));
  expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ model: "base" });
  expect(screen.getByText(/About 145 MB to download/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("radio", { name: "Processor only" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "PUT")).toHaveLength(2));
  expect(calls.filter((c) => c.method === "PUT")[1].body).toEqual({ device: "cpu" });
});

// ---------- notes, approving and clearing: everything the AI does is on this page ----------

const notesOverview = (waiting: number, isCloud = false) => ({
  counts: { waiting, processed: 3, unsorted: 1, suggested: 1, tag_suggested: 1, untagged: 0, ai_filed: 4, ai_tagged: 7 },
  ai_label: isCloud ? "Claude · claude-haiku-5-5" : "Ollama · gemma4:12b",
  is_cloud: isCloud,
  cloud_batch_limit: 50,
});
const sortSettings = {
  auto_sort: false, auto_tag: false, auto_notes: false, look_at_pictures: true, mode: "my_list",
  platform_collections: "hint", max_collections: 2, rules: [], review_below: 0.6, kind_steps: {},
  ai_folder: "", tags_per_video: 6, tag_mode: "free", my_tags: [],
};
const notesJob = (overrides: Record<string, unknown>) =>
  makeJob({ id: 9, kind: "notes", title: "AI notes for 230 videos", status: "queued", total: 230, ...overrides });
const unsure = {
  id: 13, platform: "tiktok", platform_name: "TikTok", url: "https://t/13", author: "clips", duration_s: 20, status: "processed",
  has_thumbnail: false, title: "4k 60fps Video Clip", caption: null, summary: "A clip.", kind: "other", kind_label: "Anything else",
  facts: [], steps: [], tags: [], collections: [], error: null,
  suggestions: [{ name: "Music", confidence: 0.75 }], tag_suggestions: ["video", "editing"],
};
const music = {
  id: 4, name: "Music", origin: "mine", description: null, position: 1, count: 2, parent_id: null, space_id: 1,
  ai_allowed: true, color: null, collapsed: false, path: "Music", depth: 0, has_children: false,
};
const gym = { ...music, id: 5, name: "Gym", path: "Gym", position: 2 };
const pipeline = (extra: Record<string, unknown> = {}) => ({
  "GET /api/enrich/recent": [],
  "GET /api/enrich": overview(),
  "GET /api/jobs": [],
  "GET /api/notes/overview": notesOverview(230),
  "GET /api/sorting/settings": { settings: sortSettings, kinds: [] },
  "PATCH /api/sorting/settings": (body: unknown) => ({ settings: { ...sortSettings, ...(body as object) }, kinds: [] }),
  "GET /api/library?view=unsorted": [unsure],
  "GET /api/collections": { collections: [music, gym], spaces: [{ id: 1, name: "My saves", color: null, position: 1, collections: 2 }], counts: {}, limit: 50 },
  ...extra,
});

test("notes are written on the same page: next 200, live progress, and by themselves after transcripts", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend(pipeline({ "POST /api/notes/start": notesJob({}) }));
  render(<TranscriptsPage />);
  expect(await screen.findByRole("heading", { name: "Sort" })).toBeInTheDocument();
  expect(await screen.findByTestId("notes-waiting")).toHaveTextContent("230 saves have a transcript and are waiting for notes.");

  fireEvent.click(screen.getByRole("button", { name: "Write next 200" }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/notes/start")?.body).toEqual({ count: 200, confirm_cost: false }));
  act(() => {
    FakeEventSource.last?.emit("job", notesJob({ status: "running", progress: 3, total: 200, message: "Writing notes for video 4 of 200…" }));
  });
  expect(await screen.findByText("Writing notes for video 4 of 200…")).toBeInTheDocument();

  const auto = screen.getByRole("switch", { name: /Write notes by themselves when transcripts finish/ });
  expect(auto).not.toBeChecked();
  fireEvent.click(auto);
  await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ auto_notes: true }));
});

test("the AI only suggests unless switched on: two checkboxes for collections and tags", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend(pipeline());
  render(<TranscriptsPage />);
  const collections = await screen.findByRole("switch", { name: /Put into collections automatically/ });
  const tags = screen.getByRole("switch", { name: /Add tags automatically/ });
  await waitFor(() => expect(collections).toBeEnabled());
  expect(collections).not.toBeChecked();
  expect(tags).not.toBeChecked();
  expect(screen.getByText(/Other matches stay suggestions/)).toBeInTheDocument();
  fireEvent.click(collections);
  await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ auto_sort: true }));
});

test("a cloud AI asks before notes spend money, does 50 at most, and never starts by itself", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend(pipeline({
    "GET /api/notes/overview": notesOverview(230, true),
    "POST /api/notes/start": (body: unknown) =>
      (body as { confirm_cost: boolean }).confirm_cost
        ? notesJob({ status: "done" })
        : httpError(409, { code: "confirm_cost", detail: "This sends about 50 requests to Claude, which your API key pays for. Continue?" }),
  }));
  render(<TranscriptsPage />);
  expect(await screen.findByText(/A cloud AI does at most 50 at a time/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Write next 200" })).not.toBeInTheDocument();
  expect(screen.getByRole("switch", { name: /Write notes by themselves/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Write next 50" }));
  expect(await screen.findByText(/which your API key pays for/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Yes, go ahead" }));
  await waitFor(() => expect(calls.filter((c) => c.url === "/api/notes/start")[1]?.body).toEqual({ count: 50, confirm_cost: true }));
});

test("approve on the same page: accept the AI's pick, choose another, or add its tags", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend(pipeline({
    "POST /api/review/13/accept": { ...unsure, collections: [{ id: 4, name: "Music", origin: "mine", source: "user", confidence: null }] },
    "POST /api/items/13/tag-suggestions": { ...unsure, tags: ["video"], tag_suggestions: ["editing"] },
  }));
  render(<TranscriptsPage />);
  const unsorted = await screen.findByRole("region", { name: "Unsorted" });
  const row = await within(unsorted).findByTestId("unsorted-13");
  expect(within(row).getByText("Music")).toBeInTheDocument();
  expect(within(row).getByText("(likely)")).toBeInTheDocument();
  fireEvent.click(within(row).getByRole("button", { name: "Accept" }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/review/13/accept")?.body).toEqual({}));

  fireEvent.click(within(row).getByRole("button", { name: "Choose another" }));
  const picker = await screen.findByRole("dialog", { name: /Choose a collection/ });
  fireEvent.click(within(picker).getByRole("button", { name: /Gym/ }));
  await waitFor(() => expect(calls.filter((c) => c.url === "/api/review/13/accept")[1]?.body).toEqual({ collection_id: 5 }));

  fireEvent.click(within(row).getByRole("button", { name: "Add #video" }));
  await waitFor(() =>
    expect(calls.find((c) => c.url === "/api/items/13/tag-suggestions")?.body).toEqual({ names: ["video"], accept: true }),
  );
});

test("clear what the AI did: each asks first, and the user's own work stays", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend(pipeline({ "POST /api/sorting/clear": { cleared: 7 } }));
  render(<TranscriptsPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Remove its tags (7)" }));
  fireEvent.click(await screen.findByRole("button", { name: "Clear" }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/sorting/clear")?.body).toEqual({ what: "ai_tags" }));
  expect(screen.getByRole("button", { name: "Undo its placements (4)" })).toBeInTheDocument();
});


test("unavailable saves can be rechecked even when all imported saves were marked unavailable", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const calls = fakeBackend({
    "GET /api/enrich/recent": [],
    "GET /api/enrich": overview({ total: 0, waiting: 0, gone: 434 }),
    "GET /api/jobs": [],
    "POST /api/enrich/start": enrichJob({ title: "Retry 434 videos", total: 434 }),
  });
  render(<TranscriptsPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Recheck 434 unavailable" }));
  await waitFor(() => expect(calls.find((call) => call.url === "/api/enrich/start")?.body)
    .toEqual({ count: null, which: "unavailable" }));
});
