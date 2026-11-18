// Tests for tags, selecting many saves, and the sidebar choices.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { DEFAULT_LOOK, type Look } from "../../lib/theme";
import TagsPage from "../../pages/TagsPage";
import LibraryPage from "../../pages/LibraryPage";
import { FakeEventSource, fakeBackend } from "../../test/fakeBackend";
import { libraryItem } from "../../test/libraryItem";
import AppearanceSettings from "../look/AppearanceSettings";
import { arrangeNav, movedNav } from "./tree";

beforeEach(() => {
  window.location.hash = "";
});

test("sidebar pages keep the saved order, and Settings can't be hidden", () => {
  const pages = ["/", "/library", "/tags", "/settings"].map((path) => ({ path }));
  expect(arrangeNav(pages, ["/tags", "/"], ["/library", "/settings"]).map((p) => p.path)).toEqual(["/tags", "/", "/settings"]);
  expect(movedNav(["/", "/library", "/tags"], "/tags", "/", false)).toEqual(["/tags", "/", "/library"]);
  expect(movedNav(["/", "/library", "/tags"], "/", "/tags", true)).toEqual(["/library", "/tags", "/"]);
});

test("sidebar choices: hide a page, move one, quick buttons, closed tips", () => {
  const changes: Partial<Look>[] = [];
  render(
    <AppearanceSettings look={{ ...DEFAULT_LOOK, dismissed_tips: ["a", "b"] }} onChange={(change) => changes.push(change)} />,
  );
  fireEvent.click(screen.getByLabelText("Show Plans"));
  fireEvent.click(screen.getByLabelText("Move Library down"));
  fireEvent.click(screen.getByLabelText(/Quick buttons on saves/));
  fireEvent.click(screen.getByRole("button", { name: "Show the 2 closed tips again" }));
  expect(changes[0]).toEqual({ nav_hidden: ["/plans"] });
  const order = (changes[1] as { nav_order: string[] }).nav_order;
  expect(order.indexOf("/library")).toBe(order.indexOf("/collections") + 1);
  expect(order.slice(-3)).toEqual(["/import", "/transcripts", "/settings"]); // Manage stays apart
  expect(changes[2]).toEqual({ card_actions: false });
  expect(changes[3]).toEqual({ dismissed_tips: [] });
  expect(screen.queryByLabelText("Move Archive down")).toBeDisabled(); // the last of its section
});

test("the tags page renames, merges and deletes tags", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const tags = [
    { id: 1, name: "pasta", color: null, count: 4 },
    { id: 2, name: "gym", color: "rose", count: 9 },
  ];
  const calls = fakeBackend({
    "GET /api/tags": { tags },
    "PATCH /api/tags/1": { tags: [tags[1], { ...tags[0], name: "italian" }] },
    "DELETE /api/tags/2": { tags: [tags[0]] },
    "POST /api/tags/merge": { tags: [{ ...tags[0], name: "food" }] },
    "POST /api/tags": { tags: [...tags, { id: 3, name: "japan", color: null, count: 0 }] },
    "GET /api/jobs": [],
  });
  render(<TagsPage />);
  const rows = await screen.findAllByRole("listitem");
  expect(rows.map((r) => r.dataset.testid)).toEqual(["tag-gym", "tag-pasta"]); // most used first
  expect(screen.getByText("#pasta").closest("a")).toHaveAttribute("href", "#/library?tags=pasta");

  const pasta = screen.getByTestId("tag-pasta");
  fireEvent.click(within(pasta).getByRole("button", { name: "Rename" }));
  fireEvent.change(screen.getByLabelText("New name for #pasta"), { target: { value: "italian" } });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((x) => x.method === "PATCH")?.body).toEqual({ name: "italian" }));

  fireEvent.click(within(screen.getByTestId("tag-gym")).getByRole("button", { name: "Delete" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete #gym" }));
  await waitFor(() => expect(calls.some((x) => x.method === "DELETE" && x.url === "/api/tags/2")).toBe(true));

  fireEvent.change(screen.getByLabelText("New tag name"), { target: { value: "japan" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.find((x) => x.method === "POST" && x.url === "/api/tags")?.body).toEqual({ name: "japan" }));

  // Pick two and merge them into one name.
  fireEvent.click(screen.getByLabelText("Pick #pasta"));
  fireEvent.click(screen.getByLabelText("Pick #gym"));
  const bar = screen.getByRole("toolbar", { name: "Picked tags" });
  fireEvent.change(within(bar).getByLabelText("Merge the picked tags into"), { target: { value: "food" } });
  fireEvent.click(within(bar).getByRole("button", { name: "Merge" }));
  await waitFor(() => expect(calls.find((x) => x.url === "/api/tags/merge")?.body).toEqual({ tag_ids: [1, 2], into: "food" }));
});

test("select several saves in the library and tag them all at once", async () => {
  window.location.hash = "#/library";
  const calls = fakeBackend({
    "GET /api/library/filters": {
      platforms: [], kinds: [], collections: [], tags: [{ id: "pasta", label: "pasta", count: 1 }], no_collection: 2,
    },
    "GET /api/library/items": { total: 2, offset: 0, items: [libraryItem(), libraryItem({ id: 2, title: "Lisbon guide" })] },
    "GET /api/collections": { collections: [], counts: { waiting: 0, processed: 0, review: 0, unsorted: 0 } },
    "POST /api/items/bulk": { changed: 2, items: [] },
  });
  render(<LibraryPage />);
  expect(await screen.findByText("Lisbon guide")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Select" }));
  fireEvent.click(screen.getByTestId("library-1"));
  fireEvent.click(screen.getByTestId("library-2"));
  const bar = screen.getByRole("toolbar", { name: "Selected saves" });
  expect(within(bar).getByText("2 selected")).toBeInTheDocument();
  fireEvent.change(within(bar).getByLabelText("Tag for the selected saves"), { target: { value: "weekend" } });
  fireEvent.click(within(bar).getByRole("button", { name: "Add tag" }));
  await waitFor(() => expect(calls.some((x) => x.url === "/api/items/bulk")).toBe(true));
  expect(calls.find((x) => x.url === "/api/items/bulk")?.body).toEqual({ item_ids: [1, 2], action: "add_tag", tag: "weekend" });

  // The "in no collection" filter goes in the address.
  fireEvent.change(screen.getByLabelText("Collection"), { target: { value: "none" } });
  expect(window.location.hash).toContain("collection_id=none");
  await vi.waitFor(() => expect(calls.some((x) => x.url.includes("in_collection=none"))).toBe(true));
});

test("right-click a tag to merge it into another; the tag limit shows", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  const tags = [
    { id: 1, name: "pasta", color: null, count: 3, by_user: 1, by_ai: 2, by_app: 0 },
    { id: 2, name: "gym", color: null, count: 1, by_user: 1, by_ai: 0, by_app: 0 },
  ];
  const calls = fakeBackend({
    "GET /api/tags": { tags, per_save: 10, limit: 100, total: 2 },
    "GET /api/notes/overview": { counts: { untagged: 0 } },
    "POST /api/tags/merge": { tags: [tags[1]] },
    "GET /api/jobs": [],
  });
  render(<TagsPage />);
  expect(await screen.findByText("(2 of 100 used)")).toBeInTheDocument();
  fireEvent.contextMenu(screen.getByTestId("tag-pasta"), { clientX: 10, clientY: 10 });
  fireEvent.click(within(await screen.findByRole("menu", { name: "#pasta" })).getByRole("menuitem", { name: "Merge into…" }));
  const dialog = await screen.findByRole("dialog", { name: "Merge #pasta" });
  fireEvent.click(within(dialog).getByRole("button", { name: "Merge" }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/tags/merge")?.body).toEqual({ tag_ids: [1, 2], into: "gym" }));
});

test("the Tags page is for tagging by hand: the AI's tag ideas wait on the Sort page", async () => {
  fakeBackend({
    "GET /api/tags": { tags: [{ id: 1, name: "pasta", color: null, count: 3 }], per_save: 10, limit: 100, total: 1 },
    "GET /api/notes/overview": { counts: { untagged: 44, processed: 60, tag_suggested: 12 } },
    "GET /api/jobs": [],
  });
  render(<TagsPage />);
  expect(await screen.findByText(/The AI suggests tags for 12 saves/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Add them on the Sort page" })).toHaveAttribute("href", "#/transcripts");
  expect(screen.queryByRole("button", { name: /Let the AI tag/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /AI tags/ })).not.toBeInTheDocument();
});
