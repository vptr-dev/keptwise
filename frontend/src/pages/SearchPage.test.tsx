import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import SearchBar from "../features/search/SearchBar";
import { markWords, whereIn } from "../features/search/searchApi";
import { FakeEventSource, fakeBackend } from "../test/fakeBackend";
import SearchPage from "./SearchPage";

const card = (overrides: Record<string, unknown> = {}) => ({
  id: 1, platform: "tiktok", platform_name: "TikTok", url: "https://www.tiktok.com/@x/video/1", author: "chef",
  duration_s: 60, status: "processed", has_thumbnail: false, title: "Easy carbonara", caption: "Easy carbonara",
  summary: "A quick pasta dinner.", kind: "recipe", kind_label: "Recipe", facts: [], steps: ["Boil pasta"],
  tags: [], needs_review: false, review_reason: null, suggestions: [], new_collection: null, error: null,
  collections: [], ...overrides,
});

const status = (overrides: Record<string, unknown> = {}) => ({
  model_ready: true, model_bytes: 67e6, items_with_text: 20, waiting: 0, job: null, ...overrides,
});

const pastaResult = {
  item: card(),
  found_by: ["words", "similar"],
  words: ["pasta"],
  matches: [{
    part: "transcript", label: "Transcript", at_seconds: 42,
    segments: [{ text: "then add the ", hit: false }, { text: "pasta", hit: true }, { text: " and salt", hit: false }],
  }],
  similar: { part: "transcript", label: "Transcript", text: "then add the pasta", score: 0.7, at_seconds: 42 },
};

const noodleResult = {
  item: card({ id: 2, title: "Ramen at home", kind_label: null }),
  found_by: ["similar"],
  words: [],
  matches: [],
  similar: { part: "transcript", label: "Transcript", text: "slurp the noodles", score: 0.6, at_seconds: 5 },
};

afterEach(() => {
  window.location.hash = "";
});

test("markWords and whereIn", () => {
  expect(markWords("Pasta, more pasta!", ["pasta"])).toEqual([
    { text: "Pasta", hit: true }, { text: ", more ", hit: false }, { text: "pasta", hit: true }, { text: "!", hit: false },
  ]);
  expect(markWords("a.b", ["."])).toEqual([{ text: "a.b", hit: false }]); // one-letter words are ignored
  expect(whereIn(82)).toBe("about 1:22 in");
  expect(whereIn(null)).toBeNull();
});

test("search results show highlighted words, where they are, and similar ideas", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/search?q=pasta";
  const calls = fakeBackend({
    "GET /api/search/status": status(),
    "GET /api/search?": { query: "pasta", results: [pastaResult, noodleResult], similar_ready: true },
    "GET /api/jobs": [],
    "GET /api/items/2": { item: card({ id: 2, title: "Ramen at home" }), transcript: "slurp the noodles" },
  });

  render(<SearchPage />);
  expect(await screen.findByTestId("result-count")).toHaveTextContent("2 videos");
  const mark = screen.getByText("pasta", { selector: "mark" });
  expect(mark).toBeInTheDocument();
  expect(screen.getByText(/Transcript, about 0:42 in/)).toBeInTheDocument();
  expect(screen.getByText("Matched: pasta")).toBeInTheDocument();
  expect(screen.getAllByText("Similar idea")).toHaveLength(2);
  expect(screen.getByText("slurp the noodles")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("tab", { name: "Your words" }));
  await waitFor(() => expect(calls.some((c) => c.url.includes("mode=words"))).toBe(true));

  // Opening a result shows its transcript.
  fireEvent.click(screen.getByTestId("result-2"));
  expect(await screen.findByTestId("transcript")).toHaveTextContent("slurp the noodles");
  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("nothing found, and turning on similar search", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "#/search?q=zebra";
  const calls = fakeBackend({
    "GET /api/search/status": status({ model_ready: false }),
    "POST /api/search/index": status({ model_ready: false }),
    "GET /api/search?": { query: "zebra", results: [], similar_ready: false },
    "GET /api/jobs": [],
  });
  render(<SearchPage />);
  expect(await screen.findByText(/Nothing found for “zebra”/)).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("button", { name: "Turn on similar search" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/search/index")).toBe(true));
});

test("the search bar goes to the search screen", () => {
  render(<SearchBar />);
  const box = screen.getByRole("searchbox", { name: "Search your saves" });
  fireEvent.change(box, { target: { value: "london trip" } });
  fireEvent.submit(box.closest("form")!);
  expect(window.location.hash).toBe("#/search?q=london+trip");
});
