// Tests for the Library grid, an item's page, Plans and Safe to unsave.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { paramsToQuery, queryToParams } from "../features/library/libraryApi";
import Toasts from "../components/Toasts";
import { applyTheme, nextTheme } from "../lib/theme";
import Thumb from "../features/library/Thumb";
import { fakeBackend } from "../test/fakeBackend";
import { libraryItem } from "../test/libraryItem";
import ItemPage from "./ItemPage";
import LibraryPage from "./LibraryPage";
import PlanPage from "./PlanPage";
import ArchivePage from "./ArchivePage";
import PlansPage from "./PlansPage";
import UnsavePage from "./UnsavePage";

const filters = {
  platforms: [{ id: "tiktok", label: "TikTok", count: 2 }],
  kinds: [{ id: "recipe", label: "Recipe", count: 1 }, { id: "travel", label: "Place or trip", count: 0 }],
  collections: [{ id: 3, label: "Cooking", count: 1 }],
};

beforeEach(() => {
  window.location.hash = "";
});

test("filters live in the address and only non-default ones are kept", () => {
  const query = paramsToQuery(new URLSearchParams("kind=recipe&status=bogus&sort=title"));
  expect(query.status).toBe("all"); // unknown values fall back
  expect(queryToParams(query).toString()).toBe("kind=recipe&sort=title");
});

test("the library shows saves as cards and filters change the address", async () => {
  window.location.hash = "#/library";
  const calls = fakeBackend({
    "GET /api/library/filters": filters,
    "GET /api/library/items": {
      total: 2,
      offset: 0,
      items: [libraryItem(), libraryItem({ id: 2, title: null, status: "imported", kind_label: null, steps: [], steps_checked: [] })],
    },
  });
  render(<LibraryPage />);
  expect(await screen.findByText("Easy tomato pasta")).toBeInTheDocument();
  expect(screen.getByText("TikTok video")).toBeInTheDocument(); // untitled saves still get a name
  expect(screen.getByText(/Not transcribed yet/)).toBeInTheDocument();
  expect(screen.getByText("2 saves")).toBeInTheDocument();
  expect(screen.getByTestId("library-1")).toHaveAttribute("href", "#/item/1");

  fireEvent.change(await screen.findByLabelText("Type"), { target: { value: "recipe" } });
  expect(window.location.hash).toBe("#/library?kind=recipe");
  await vi.waitFor(() => expect(calls.some((c) => c.url.includes("kind=recipe"))).toBe(true));
});

test("an empty library points to Import", async () => {
  window.location.hash = "#/library";
  fakeBackend({
    "GET /api/library/filters": filters,
    "GET /api/library/items": { total: 0, offset: 0, items: [] },
  });
  render(<LibraryPage />);
  expect(await screen.findByText("Your library is empty")).toBeInTheDocument();
  expect(screen.getByText("Import your saves")).toBeInTheDocument();
});

test("the item page ticks steps with a click or a number key, and marks it done", async () => {
  const calls = fakeBackend({
    "GET /api/items/1": { item: libraryItem(), transcript: "Hello and welcome" },
    "PUT /api/items/1/steps/0": libraryItem({ steps_checked: [true, false, false], started_at: "x" }),
    "PUT /api/items/1/steps/1": libraryItem({ steps_checked: [true, true, false], started_at: "x" }),
    "PATCH /api/items/1": libraryItem({ done: true, steps_checked: [true, true, false] }),
  });
  render(<ItemPage itemId={1} />);
  expect(await screen.findByRole("heading", { name: "Easy tomato pasta" })).toBeInTheDocument();
  expect(screen.getByText("0 of 3 done")).toBeInTheDocument();
  expect(screen.getByText("Open on TikTok").closest("a")).toHaveAttribute("href", "https://www.tiktok.com/@x/video/1");

  fireEvent.click(screen.getByLabelText("Buy tomatoes"));
  expect(await screen.findByText("1 of 3 done")).toBeInTheDocument();
  expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ done: true });

  fireEvent.keyDown(window, { key: "2" });
  expect(await screen.findByText("2 of 3 done")).toBeInTheDocument();

  fireEvent.keyDown(window, { key: "d" });
  expect(await screen.findByText("Done (undo)")).toBeInTheDocument();
  expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ done: true });
});

test("an item without notes says what to do next", async () => {
  fakeBackend({
    "GET /api/items/5": {
      item: libraryItem({ id: 5, status: "imported", title: null, steps: [], steps_checked: [], summary: null, facts: [] }),
      transcript: null,
    },
  });
  render(<ItemPage itemId={5} />);
  expect(await screen.findByText(/hasn't been transcribed yet/)).toBeInTheDocument();
  expect(screen.queryByText("Mark as done")).not.toBeInTheDocument();
});

const planSummary = (overrides: Record<string, unknown> = {}) => ({
  id: 4, name: "Weekend in Lisbon", note: null, color: null, done: false, done_at: null,
  created_at: "2026-11-10T10:00:00Z", updated_at: "2026-11-11T10:00:00Z",
  item_count: 2, items_done: 1, steps_done: 1, steps_total: 6, preview: [], platforms: ["tiktok"],
  due_on: null, pinned: false, tasks_total: 0, tasks_done: 0, ...overrides,
});

test("plans list their progress, and an empty list explains how to start", async () => {
  fakeBackend({ "GET /api/plans": { plans: [planSummary()], open: 1, finished: 0 } });
  render(<PlansPage />);
  expect(await screen.findByText("Weekend in Lisbon")).toBeInTheDocument();
  expect(screen.getByText("1 of 2 to go · 2 saves")).toBeInTheDocument();
  expect(screen.getByText(/1\/2 · 1\/6 steps/)).toBeInTheDocument();
  fireEvent.click(screen.getByText("Finished (0)"));
  expect(screen.getByText("Nothing finished yet")).toBeInTheDocument();
});

test("a new plan opens straight away", async () => {
  const calls = fakeBackend({
    "GET /api/plans": { plans: [], open: 0, finished: 0 },
    "POST /api/plans": { ...planSummary({ id: 9, name: "Meal prep" }), items: [] },
  });
  render(<PlansPage />);
  fireEvent.change(await screen.findByLabelText("New plan name"), { target: { value: "Meal prep" } });
  fireEvent.click(screen.getByRole("button", { name: /Make plan/ }));
  await vi.waitFor(() => expect(window.location.hash).toBe("#/plans/9"));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Meal prep", item_ids: [] });
});

test("a plan ticks saves off, opens their steps, reorders and adds saves", async () => {
  const two = libraryItem({ id: 2, title: "Lisbon tram tour", steps: [], steps_checked: [] });
  const details = (overrides: Record<string, unknown> = {}) => ({
    ...planSummary(),
    items: [{ item: libraryItem(), done: false, done_at: null }, { item: two, done: false, done_at: null }],
    ...overrides,
  });
  const calls = fakeBackend({
    "GET /api/plans/4": details(),
    "PUT /api/plans/4/items/1": details({ items_done: 1, items: [{ item: libraryItem(), done: true, done_at: "x" }, { item: two, done: false, done_at: null }] }),
    "POST /api/plans/4/order": details({ items: [{ item: two, done: false, done_at: null }, { item: libraryItem(), done: false, done_at: null }] }),
    "PUT /api/items/1/steps/0": libraryItem({ steps_checked: [true, false, false] }),
    "GET /api/library/items": { total: 1, offset: 0, items: [libraryItem({ id: 3, title: "Pastel de nata" })] },
    "POST /api/plans/4/items": details(),
  });
  render(<PlanPage planId={4} />);
  expect(await screen.findByRole("heading", { name: "Weekend in Lisbon" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("checkbox", { name: "Easy tomato pasta done" }));
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/plans/4/items/1")?.body).toEqual({ done: true }));
  expect(await screen.findByRole("checkbox", { name: "Easy tomato pasta done" })).toHaveAttribute("aria-checked", "true");

  fireEvent.click(screen.getByRole("button", { name: "Steps" }));
  fireEvent.click(screen.getByLabelText("Buy tomatoes"));
  await vi.waitFor(() => expect(calls.some((c) => c.url === "/api/items/1/steps/0")).toBe(true));

  fireEvent.click(screen.getAllByRole("button", { name: "Move down" })[0]);
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/plans/4/order")?.body).toEqual({ item_ids: [2, 1] }));

  fireEvent.click(screen.getByRole("button", { name: /Add saves/ }));
  fireEvent.click(await screen.findByLabelText(/Pastel de nata/));
  fireEvent.click(screen.getByRole("button", { name: "Add 1" }));
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/plans/4/items")?.body).toEqual({ item_ids: [3] }));
});

test("pinned plans come first, then the soonest day, and late plans say so", async () => {
  const calls = fakeBackend({
    "GET /api/plans": {
      plans: [
        planSummary({ id: 1, name: "Someday", updated_at: "2026-11-12T10:00:00Z" }),
        planSummary({ id: 2, name: "Overdue trip", due_on: "2020-01-01" }),
        planSummary({ id: 3, name: "Pinned one", pinned: true }),
      ],
      open: 3,
      finished: 0,
    },
    "PATCH /api/plans/1": planSummary({ id: 1, pinned: true }),
  });
  render(<PlansPage />);
  await screen.findByText("Someday");
  const names = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
  expect(names).toEqual(["Pinned one", "Overdue trip", "Someday"]);
  expect(screen.getByText(/days late/)).toBeInTheDocument();
  expect(screen.getByText("1 late")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Pin Someday" }));
  await vi.waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ pinned: true }));
});

test("a plan can start from a collection and a day", async () => {
  const calls = fakeBackend({
    "GET /api/plans": { plans: [], open: 0, finished: 0 },
    "GET /api/collections": {
      collections: [{ id: 7, name: "Lisbon", path: "Travel / Lisbon", count: 3, total: 3, depth: 1, parent_id: 1 }],
      counts: { waiting: 0, processed: 0, review: 0, unsorted: 0 },
    },
    "POST /api/plans": { ...planSummary({ id: 11, name: "Lisbon" }), items: [] },
  });
  render(<PlansPage />);
  fireEvent.change(await screen.findByLabelText("Start with the saves of a collection"), { target: { value: "7" } });
  fireEvent.change(screen.getByLabelText(/The day the new plan is for/), { target: { value: "2026-12-24" } });
  fireEvent.click(screen.getByRole("button", { name: /Make plan/ }));
  await vi.waitFor(() => expect(window.location.hash).toBe("#/plans/11"));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Lisbon", item_ids: [], collection_id: 7, due_on: "2026-12-24" });
});

test("a plan holds sections, notes per save and to-dos of your own", async () => {
  const base = {
    ...planSummary({ tasks_total: 1, tasks_done: 0 }),
    items: [
      { item: libraryItem(), done: false, done_at: null, section: null, note: null },
      { item: libraryItem({ id: 2, title: "Lisbon tram tour", steps: [], steps_checked: [] }), done: false, done_at: null, section: "Day 1", note: "Go early" },
    ],
    tasks: [{ id: 5, text: "Book the hotel", section: "Day 1", done: false, done_at: null }],
    sections: ["Day 1"],
  };
  const calls = fakeBackend({
    "GET /api/plans/4": base,
    "POST /api/plans/4/tasks": base,
    "PATCH /api/plans/4/tasks/5": { ...base, tasks_done: 1, tasks: [{ ...base.tasks[0], done: true }] },
    "PATCH /api/plans/4": { ...base, due_on: "2026-12-24" },
  });
  render(<PlanPage planId={4} />);
  const day = await screen.findByRole("region", { name: "Day 1" });
  expect(within(day).getByText("Lisbon tram tour")).toBeInTheDocument();
  expect(within(day).getByText("Note: Go early")).toBeInTheDocument();
  expect(screen.getByText("1 of 3 done · 1/6 steps")).toBeInTheDocument();

  fireEvent.click(within(day).getByRole("checkbox", { name: "Book the hotel done" }));
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/plans/4/tasks/5")?.body).toEqual({ done: true }));

  const input = screen.getByLabelText("New to-do");
  fireEvent.change(input, { target: { value: "Pack" } });
  fireEvent.submit(input.closest("form")!);
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/plans/4/tasks")?.body).toEqual({ text: "Pack", section: null }));

  fireEvent.change(screen.getByLabelText("The day this plan is for"), { target: { value: "2026-12-24" } });
  await vi.waitFor(() => expect(calls.find((c) => c.method === "PATCH" && c.url === "/api/plans/4")?.body).toEqual({ due_on: "2026-12-24" }));

  fireEvent.click(screen.getByRole("radio", { name: "All steps" }));
  expect(await screen.findByLabelText("All steps")).toBeInTheDocument();
  expect(screen.getByLabelText("Buy tomatoes")).toBeInTheDocument();
});

test("hovering a save shows quick buttons; Tags adds a tag without opening it", async () => {
  window.location.hash = "#/library";
  const calls = fakeBackend({
    "GET /api/library/filters": filters,
    "GET /api/library/items": { total: 1, offset: 0, items: [libraryItem()] },
    "GET /api/tags": { tags: [{ id: 8, name: "quick", color: null, count: 4 }] },
    "POST /api/items/1/tags": libraryItem({ tags: ["dinner", "quick"] }),
  });
  render(<LibraryPage />);
  const card = await screen.findByTestId("library-1");
  fireEvent.mouseEnter(card);
  fireEvent.click(within(card).getByRole("button", { name: "Tags for this save" }));
  const panel = await screen.findByRole("dialog", { name: "Tags" });
  fireEvent.click(await within(panel).findByRole("button", { name: "#quick" }));
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/items/1/tags")?.body).toEqual({ name: "quick" }));
  expect(window.location.hash).toBe("#/library"); // the card wasn't opened
  expect(await within(card).findByText(/#quick/)).toBeInTheDocument();
});

test("the library search box and several tags go in the address", async () => {
  window.location.hash = "#/library?tags=pasta";
  const calls = fakeBackend({
    "GET /api/library/filters": { ...filters, tags: [{ id: "pasta", label: "pasta", count: 2 }, { id: "quick", label: "quick", count: 1 }] },
    "GET /api/library/items": { total: 0, offset: 0, items: [] },
  });
  render(<LibraryPage />);
  expect(await screen.findByLabelText("Stop filtering by #pasta")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Tag"), { target: { value: "quick" } });
  expect(window.location.hash).toBe("#/library?tags=pasta%2Cquick");
  fireEvent.change(screen.getByLabelText("Find in the library"), { target: { value: "tomato" } });
  await vi.waitFor(() => expect(window.location.hash).toContain("q=tomato"));
  await vi.waitFor(() => expect(calls.some((c) => c.url.includes("q=tomato"))).toBe(true));
});

test("unsave: tick one off and export the CSV", async () => {
  const calls = fakeBackend({
    "GET /api/unsave": { rule: "processed", left: 2, items: [libraryItem(), libraryItem({ id: 2, title: "Lisbon guide" })] },
    "PATCH /api/items/2": libraryItem({ id: 2, title: "Lisbon guide", unsaved: true }),
    "POST /api/unsave/export": { path: "C:\\Users\\me\\Downloads\\saves-to-unsave-2026-11-11.csv", count: 2 },
  });
  render(<UnsavePage />);
  expect(await screen.findByText("0 of 2 unsaved")).toBeInTheDocument();
  expect(screen.getByText(/once the AI has written its notes/)).toBeInTheDocument();
  expect(screen.getByText(/never logs in to or changes anything on TikTok/)).toBeInTheDocument();

  fireEvent.click(screen.getByLabelText("I've unsaved “Lisbon guide”"));
  expect(await screen.findByText("1 of 2 unsaved")).toBeInTheDocument();
  expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ unsaved: true });

  fireEvent.click(screen.getByLabelText("Hide ones I've unsaved"));
  expect(screen.queryByText("Lisbon guide")).not.toBeInTheDocument();

  fireEvent.click(screen.getByText("Export CSV"));
  expect(await screen.findByText(/saves-to-unsave-2026-11-11.csv/)).toBeInTheDocument();
});

test("the theme puts the dark class on the page", () => {
  applyTheme("dark");
  expect(document.documentElement).toHaveClass("dark");
  applyTheme("light");
  expect(document.documentElement).not.toHaveClass("dark");
  expect(nextTheme("light")).toBe("dark");
  expect(nextTheme("dark")).toBe("system");
  expect(nextTheme("system")).toBe("light");
});

test("right-click a save: delete it and undo, or find-or-make a collection for it", async () => {
  window.location.hash = "#/library";
  const calls = fakeBackend({
    "GET /api/library/filters": filters,
    "GET /api/library/items": { total: 1, offset: 0, items: [libraryItem()] },
    "PATCH /api/items/1": libraryItem({ deleted: true }),
    "GET /api/collections": {
      collections: [{ id: 3, name: "Cooking", origin: "mine", description: null, position: 1, count: 1, parent_id: null, ai_allowed: true, color: null, collapsed: false, path: "Cooking", depth: 0, has_children: false }],
      counts: {}, limit: 50,
    },
    "POST /api/collections": { collections: [], counts: {}, created_id: 7 },
    "POST /api/items/1/move": libraryItem(),
  });
  render(
    <>
      <LibraryPage />
      <Toasts />
    </>,
  );
  const card = await screen.findByTestId("library-1");
  fireEvent.contextMenu(card, { clientX: 20, clientY: 20 });
  const menu = await screen.findByRole("menu", { name: "Easy tomato pasta" });
  expect(within(menu).getByRole("menuitem", { name: /^Select/ })).toBeInTheDocument();
  expect(within(menu).queryByRole("menuitem", { name: /Mark as done/ })).not.toBeInTheDocument();
  fireEvent.click(within(menu).getByRole("menuitem", { name: /^Delete/ }));
  await vi.waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ deleted: true }));
  expect(await screen.findByText("Deleted. It's in the Archive.")).toBeInTheDocument();
  expect(window.location.hash).toBe("#/library"); // the save wasn't opened
  fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
  await vi.waitFor(() => expect(calls.filter((c) => c.method === "PATCH")[1]?.body).toEqual({ deleted: false }));

  fireEvent.contextMenu(card, { clientX: 20, clientY: 20 });
  fireEvent.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Collections…" }));
  const panel = await screen.findByRole("dialog", { name: "Collections" });
  expect(within(panel).getByText("In 1 of up to 10.")).toBeInTheDocument();
  fireEvent.change(within(panel).getByLabelText("Find or make a collection"), { target: { value: "Desserts" } });
  expect(await within(panel).findByText(/Press Enter to make “Desserts” \(49 left\)/)).toBeInTheDocument();
  fireEvent.submit(within(panel).getByLabelText("Find or make a collection"));
  await vi.waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/api/collections")?.body).toEqual({ name: "Desserts", parent_id: null }));
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/items/1/move")?.body).toEqual({ from_id: null, to_id: 7 }));
});

test("pick several saves with the boxes; right-click them to ask the AI, or delete them together", async () => {
  window.location.hash = "#/library";
  const three = [libraryItem(), libraryItem({ id: 2, title: "Lisbon tram tour" }), libraryItem({ id: 3, title: "Leg day" })];
  const calls = fakeBackend({
    "GET /api/library/filters": filters,
    "GET /api/library/items": { total: 3, offset: 0, items: three },
    "GET /api/collections": { collections: [], counts: {} },
    "GET /api/plans": { plans: [], open: 0, finished: 0 },
    "POST /api/items/bulk": { changed: 3, items: [] },
  });
  render(
    <>
      <LibraryPage />
      <Toasts />
    </>,
  );
  // Every save has a select box; Shift picks the run in between.
  fireEvent.click(await screen.findByRole("checkbox", { name: "Select Easy tomato pasta" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Leg day" }), { shiftKey: true });
  const bar = await screen.findByRole("toolbar", { name: "Selected saves" });
  expect(bar).toHaveTextContent("3 selected");
  expect(within(bar).queryByRole("button", { name: "Mark done" })).not.toBeInTheDocument();

  fireEvent.contextMenu(screen.getByTestId("library-2"), { clientX: 30, clientY: 30 });
  const menu = await screen.findByRole("menu");
  fireEvent.click(within(menu).getByRole("menuitem", { name: "Ask the AI Assistant about these 3" }));
  expect(window.location.hash).toBe("#/chat?items=1,2,3");

  window.location.hash = "#/library";
  fireEvent.click(within(bar).getByRole("button", { name: "Delete" }));
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/items/bulk")?.body).toEqual({ action: "delete", item_ids: [1, 2, 3] }));
  fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
  await vi.waitFor(() => expect(calls.filter((c) => c.url === "/api/items/bulk")[1]?.body).toEqual({ item_ids: [1, 2, 3], action: "restore" }));
});

test("the Archive: put a deleted save back, or delete it for good after asking", async () => {
  const gone = libraryItem({ id: 5, title: "Old recipe", deleted: true, deleted_at: "2026-11-15T10:00:00Z" });
  const calls = fakeBackend({
    "GET /api/library/items": { total: 1, offset: 0, items: [gone] },
    "GET /api/archive": { deleted: 1, unsaved: 4 },
    "POST /api/items/bulk": { changed: 1, items: [] },
  });
  render(<ArchivePage />);
  expect(await screen.findByText("Old recipe")).toBeInTheDocument();
  expect(calls.find((c) => c.url.startsWith("/api/library/items"))?.url).toContain("archive=deleted");
  expect(screen.getByRole("tab", { name: /Unsaved/ })).toHaveTextContent("4");

  fireEvent.contextMenu(screen.getByTestId("library-5"), { clientX: 10, clientY: 10 });
  fireEvent.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Put back in the Library" }));
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/items/bulk")?.body).toEqual({ item_ids: [5], action: "restore" }));

  fireEvent.click(screen.getByRole("checkbox", { name: "Select Old recipe" }));
  fireEvent.click(within(screen.getByRole("toolbar", { name: "Picked saves" })).getByRole("button", { name: "Delete for good…" }));
  const sure = await screen.findByRole("dialog", { name: "Delete “Old recipe” for good?" });
  expect(calls.filter((c) => c.url === "/api/items/bulk")).toHaveLength(1); // not yet: it asks first
  fireEvent.click(within(sure).getByRole("button", { name: "Delete for good" }));
  await vi.waitFor(() => expect(calls.filter((c) => c.url === "/api/items/bulk")[1]?.body).toEqual({ item_ids: [5], action: "purge" }));
});

test("the Archive lists what you've unsaved, and one can be marked as still saved", async () => {
  const cleared = libraryItem({ id: 6, title: "Tram tour", unsaved: true, unsaved_at: "2026-11-15T10:00:00Z" });
  const calls = fakeBackend({
    "GET /api/library/items": { total: 1, offset: 0, items: [cleared] },
    "GET /api/archive": { deleted: 0, unsaved: 1 },
    "POST /api/items/bulk": { changed: 1, items: [] },
  });
  render(<ArchivePage tab="unsaved" />);
  expect(await screen.findByText("Tram tour")).toBeInTheDocument();
  expect(calls.find((c) => c.url.startsWith("/api/library/items"))?.url).toContain("archive=unsaved");
  fireEvent.contextMenu(screen.getByTestId("library-6"), { clientX: 10, clientY: 10 });
  fireEvent.click(within(await screen.findByRole("menu")).getByRole("menuitem", { name: "Still saved on TikTok" }));
  await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/items/bulk")?.body).toEqual({ item_ids: [6], action: "still_saved" }));
});

test("a save's picture shows the greyed logo until it loads, and again if it can't load", () => {
  const { container, rerender } = render(<Thumb item={libraryItem({ has_thumbnail: false })} />);
  expect(screen.getByRole("img", { name: /No picture yet/ })).toBeInTheDocument();
  expect(container.querySelector('img[src*="/thumbnail"]')).toBeNull();

  rerender(<Thumb item={libraryItem({ id: 7, has_thumbnail: true })} />);
  const picture = container.querySelector('img[src="/api/items/7/thumbnail"]')!;
  expect(picture).toHaveClass("opacity-0"); // the logo shows through while it loads
  fireEvent.load(picture);
  expect(picture).toHaveClass("opacity-100");
  expect(container.querySelector(".grayscale")).toBeNull();
  fireEvent.error(picture);
  expect(screen.getByRole("img", { name: /No picture yet/ })).toBeInTheDocument();
});

test("changing the theme without the reveal effect still changes it", async () => {
  const { revealTheme, themeButtonSpot } = await import("../lib/theme");
  const change = vi.fn();
  revealTheme(change); // this test window has no view transitions
  expect(change).toHaveBeenCalledTimes(1);
  expect(themeButtonSpot()).toEqual({ x: window.innerWidth / 2, y: window.innerHeight / 2 });
});
