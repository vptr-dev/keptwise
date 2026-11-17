// Tests for the command centre.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { fakeBackend } from "../../test/fakeBackend";
import { libraryItem } from "../../test/libraryItem";
import CommandPalette, { matchScore, type CommandAction } from "./CommandPalette";

const filters = {
  platforms: [], kinds: [], no_collection: 0,
  collections: [{ id: 3, label: "Cooking", count: 4 }, { id: 4, label: "Travel / Lisbon", count: 2 }],
  tags: [{ id: "dinner", label: "dinner", count: 2 }, { id: "travel", label: "travel", count: 9 }],
  creators: [{ id: "sam", label: "@sam", count: 5 }],
};

beforeEach(() => {
  window.location.hash = "";
});

function open(actions: CommandAction[] = []) {
  const onClose = vi.fn();
  render(<CommandPalette actions={actions} onClose={onClose} />);
  return { onClose, box: screen.getByRole("combobox") };
}

test("every word typed has to match, and the start of a word counts most", () => {
  expect(matchScore("Go to Library", "lib go")).toBeGreaterThan(0);
  expect(matchScore("Go to Library", "plans")).toBe(0);
  expect(matchScore("Dark theme", "dark")).toBeGreaterThan(matchScore("Slim sidebar dark", "dark"));
});

test("empty, it lists things to do and the prefixes; arrows choose and Enter runs", async () => {
  fakeBackend({ "GET /api/library/filters": filters });
  const dark = vi.fn();
  const { box, onClose } = open([
    { id: "a", label: "Go to Library", icon: null, run: vi.fn() },
    { id: "b", label: "Dark theme", icon: null, run: dark },
  ]);
  expect(box).toHaveFocus();
  expect(screen.getByRole("button", { name: /Tags/ })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: /Go to Library/ })).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(box, { key: "ArrowDown" });
  expect(screen.getByRole("option", { name: /Dark theme/ })).toHaveAttribute("aria-selected", "true");
  fireEvent.keyDown(box, { key: "Enter" });
  expect(dark).toHaveBeenCalled();
  expect(onClose).toHaveBeenCalled();
});

test("words find saves, collections, tags and actions; the first row searches everything", async () => {
  const calls = fakeBackend({
    "GET /api/library/filters": filters,
    "GET /api/library/items": { total: 1, offset: 0, items: [libraryItem({ id: 8, title: "Lisbon travel tips" })] },
  });
  const { box } = open([{ id: "a", label: "Go to Travel plans", icon: null, run: vi.fn() }]);
  fireEvent.change(box, { target: { value: "travel" } });
  expect(await screen.findByRole("option", { name: /Lisbon travel tips/ })).toBeInTheDocument();
  expect(calls.some((c) => c.url.includes("q=travel"))).toBe(true);
  expect(screen.getByRole("option", { name: /#travel/ })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: /Travel \/ Lisbon/ })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: /Go to Travel plans/ })).toBeInTheDocument();
  fireEvent.keyDown(box, { key: "Enter" });
  expect(window.location.hash).toBe("#/search?q=travel");
});

test("prefixes: @ is creators, ? asks the AI, > is actions only; Esc empties then closes", async () => {
  fakeBackend({ "GET /api/library/filters": filters });
  const { box, onClose } = open([{ id: "a", label: "Import saves", icon: null, run: vi.fn() }]);
  fireEvent.change(box, { target: { value: "@sa" } });
  fireEvent.click(await screen.findByRole("option", { name: /@sam/ }));
  expect(window.location.hash).toBe("#/library?creator=sam");

  fireEvent.change(box, { target: { value: "?what to cook tonight" } });
  expect(screen.getAllByRole("option")).toHaveLength(1);
  fireEvent.keyDown(box, { key: "Enter" });
  expect(window.location.hash).toBe("#/chat?q=what+to+cook+tonight");

  fireEvent.change(box, { target: { value: ">imp" } });
  expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["Import saves"]);

  onClose.mockClear();
  fireEvent.keyDown(box, { key: "Escape" });
  expect(box).toHaveValue("");
  expect(onClose).not.toHaveBeenCalled();
  fireEvent.keyDown(box, { key: "Escape" });
  expect(onClose).toHaveBeenCalled();
});
