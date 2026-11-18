// Tests for unsaving one by one, Settings -> Storage and Appearance, and the Home greeting.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import AppearanceSettings from "../features/look/AppearanceSettings";
import StorageSettings from "../features/storage/StorageSettings";
import { DEFAULT_LOOK, applyLook, type Look } from "../lib/theme";
import { fakeBackend } from "../test/fakeBackend";
import { libraryItem } from "../test/libraryItem";
import LibraryPage from "./LibraryPage";
import SettingsPage from "./SettingsPage";
import UnsavePage from "./UnsavePage";

beforeEach(() => {
  window.location.hash = "";
});

test("unsave one by one opens each save in the browser and ticks it off", async () => {
  const calls = fakeBackend({
    "GET /api/unsave": { rule: "processed", left: 2, items: [libraryItem(), libraryItem({ id: 2, title: "Lisbon guide" })] },
    "POST /api/items/": { opened: true },
    "PATCH /api/items/1": libraryItem({ unsaved: true }),
    "PATCH /api/items/2": libraryItem({ id: 2, title: "Lisbon guide", unsaved: true }),
  });
  render(<UnsavePage />);
  fireEvent.click(await screen.findByText("Unsave one by one"));
  expect(await screen.findByText("1 of 2")).toBeInTheDocument();
  const opened = () => calls.filter((c) => c.method === "POST" && c.url.endsWith("/open")).map((c) => c.url);
  expect(opened()).toEqual(["/api/items/1/open"]);

  fireEvent.click(screen.getByText("Done, open the next one"));
  expect(await screen.findByText("2 of 2")).toBeInTheDocument();
  expect(opened()).toEqual(["/api/items/1/open", "/api/items/2/open"]);
  expect(screen.getByText("1 of 2 unsaved")).toBeInTheDocument();

  fireEvent.click(screen.getByText("Done"));
  expect(await screen.findByText(/All done. You unsaved 2 videos/)).toBeInTheDocument();
});

test("storage lists models and asks before deleting one", async () => {
  const model = { id: "ollama:gemma4:12b", group: "AI models", label: "gemma4:12b", bytes: 8e9, note: "Your current AI model.", can_delete: true, in_use: true };
  const db = { id: "database", group: "Files", label: "Your saves, notes and transcripts", bytes: 2e6, note: "Never deleted.", can_delete: false, in_use: false };
  const calls = fakeBackend({
    "GET /api/storage": { entries: [model, db], data_folder: "C:\\Users\\me\\AppData\\Roaming\\Keptwise" },
    "DELETE /api/storage/": { entries: [db], data_folder: "C:\\Users\\me\\AppData\\Roaming\\Keptwise" },
  });
  render(<StorageSettings />);
  expect(await screen.findByText("gemma4:12b")).toBeInTheDocument();
  expect(screen.getByText("In use")).toBeInTheDocument();
  expect(screen.getAllByText("Delete")).toHaveLength(1); // the database can't be deleted
  fireEvent.click(screen.getByText("Delete"));
  fireEvent.click(screen.getByText("Yes, delete"));
  expect(await screen.findByText("Your saves, notes and transcripts")).toBeInTheDocument();
  expect(screen.queryByText("gemma4:12b")).not.toBeInTheDocument();
  expect(calls.find((c) => c.method === "DELETE")?.url).toBe("/api/storage/ollama%3Agemma4%3A12b");
});

test("appearance choices are passed on, and the look is put on the page", () => {
  const changes: Partial<Look>[] = [];
  render(<AppearanceSettings look={DEFAULT_LOOK} onChange={(c) => changes.push(c)} />);
  fireEvent.click(screen.getByRole("button", { name: "Accent colour: Default. Change" }));
  fireEvent.click(screen.getByRole("radio", { name: "Teal" }));
  fireEvent.click(screen.getByRole("radio", { name: "Large" }));
  fireEvent.click(screen.getByLabelText(/Slim sidebar/));
  fireEvent.click(screen.getByRole("radio", { name: "Bigger" }));
  expect(changes).toEqual([{ accent: "teal" }, { text_size: "large" }, { compact_sidebar: true }, { card_size: "large" }]);

  applyLook({ ...DEFAULT_LOOK, accent: "rose", text_size: "small", theme: "dark" });
  expect(document.documentElement.dataset.accent).toBe("rose");
  expect(document.documentElement.dataset.textSize).toBe("small");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
});

test("the library greets the user by name", async () => {
  fakeBackend({
    "GET /api/library/filters": { platforms: [], kinds: [], collections: [], tags: [], creators: [], no_collection: 0 },
    "GET /api/library/items": { total: 0, offset: 0, items: [] },
  });
  render(<LibraryPage name="Sam" />);
  expect(await screen.findByText(/^Good (morning|afternoon|evening), Sam$/)).toBeInTheDocument();
});

test("settings can be searched, and only matching sections are shown", async () => {
  fakeBackend({});
  render(<SettingsPage overview={null} onAiChange={() => undefined} look={DEFAULT_LOOK} onLookChange={() => undefined} />);
  expect(screen.getByRole("region", { name: "Appearance" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Find a setting"), { target: { value: "dark" } });
  expect(screen.queryByRole("region", { name: "Storage" })).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Appearance" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Appearance: Dark mode");
  fireEvent.change(screen.getByLabelText("Find a setting"), { target: { value: "zzzz" } });
  expect(screen.getByText(/No setting matches/)).toBeInTheDocument();
});

test("storage can clear the backups, the saves or everything, and asks first", async () => {
  const base = { entries: [], data_folder: "C:\data", saves: 12, backups: 2, backups_bytes: 4_000_000 };
  const calls = fakeBackend({
    "GET /api/storage": base,
    "POST /api/storage/clear": { ...base, saves: 0, cleared: { saves: 12 } },
  });
  render(<StorageSettings />);
  expect(await screen.findByText(/You have 12 saves and 2 backups/)).toBeInTheDocument();
  const row = screen.getByText("Clear my saves").closest("li")!;
  fireEvent.click(within(row).getByRole("button", { name: "Clear…" }));
  expect(calls.some((c) => c.method === "POST")).toBe(false); // nothing happens until you say yes
  fireEvent.click(within(row).getByRole("button", { name: "Yes, delete" }));
  expect(await screen.findByText("Deleted 12 saves.")).toBeInTheDocument();
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ what: "saves" });
  expect(within(screen.getByText("Clear my saves").closest("li")!).getByRole("button", { name: "Nothing to clear" })).toBeDisabled();
});
