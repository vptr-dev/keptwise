import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import SortingSettings, { CollectionSortOptions } from "../features/sorting/SortingSettings";
import { FakeEventSource, fakeBackend, httpError } from "../test/fakeBackend";
import { libraryItem } from "../test/libraryItem";
import CollectionsPage from "./CollectionsPage";

const collection = (id: number, name: string, count = 0, extra: Record<string, unknown> = {}) => ({
  id, name, origin: "mine", description: null, position: id, count, total: count, space_id: 1,
  parent_id: null, ai_allowed: true, color: null, collapsed: false, depth: 0, path: name, has_children: false, ...extra,
});

const spaces = [
  { id: 1, name: "My saves", color: null, position: 1, collections: 4 },
  { id: 2, name: "Work", color: "teal", position: 2, collections: 1 },
];

// Study (with Chemistry inside it), Want to go and Music in "My saves"; Decks in "Work".
const tree = [
  collection(1, "Study", 3, { total: 5, has_children: true }),
  collection(4, "Chemistry", 2, { parent_id: 1, depth: 1, path: "Study / Chemistry" }),
  collection(2, "Want to go", 3),
  collection(3, "Music", 1),
  collection(5, "Decks", 0, { space_id: 2 }),
];

const overview = (counts: Partial<Record<string, number>> = {}) => ({
  collections: tree,
  spaces,
  counts: { waiting: 20, processed: 0, unsorted: 0, ...counts },
  limit: 50, per_save: 10, space_limit: 8, depth_limit: 5,
});

const notesOverview = (waiting = 20, isCloud = false) => ({
  counts: { waiting, processed: 0, unsorted: 0 },
  ai_label: isCloud ? "Claude · claude-haiku-5-5" : "Ollama · gemma4:12b",
  is_cloud: isCloud,
  cloud_batch_limit: 50,
});

const card = (overrides: Record<string, unknown>) => ({
  id: 1, platform: "tiktok", platform_name: "TikTok", url: "https://t/1", author: "study.notes", duration_s: 30,
  status: "processed", has_thumbnail: false, title: "Chemistry notes for GCSE", caption: "notes", summary: "Revision notes.",
  kind: "learning", kind_label: "Tip or lesson", facts: ["Atoms have protons"], steps: ["Make flashcards"], tags: ["gcse"],
  suggestions: [], tag_suggestions: [], error: null,
  collections: [{ id: 1, name: "Study", origin: "mine", source: "ai", confidence: 0.95 }], ...overrides,
});

const sortSettings = {
  auto_sort: false, auto_tag: false, mode: "my_list", platform_collections: "hint", max_collections: 2, rules: [], review_below: 0.6,
  kind_steps: { recipe: "Ingredients and steps." }, ai_folder: "", tags_per_video: 6, tag_mode: "free", my_tags: [],
};
const kinds = [{ id: "recipe", label: "Recipe", default: "Ingredients and steps." }];

/** The routes every screen of the page asks for. */
const base = (extra: Record<string, unknown> = {}) => ({
  "GET /api/collections": overview(),
  "GET /api/notes/overview": notesOverview(0),
  "GET /api/jobs": [],
  "GET /api/sorting/settings": { settings: sortSettings, kinds },
  "PATCH /api/sorting/settings": (body: unknown) => ({ settings: { ...sortSettings, ...(body as object) }, kinds }),
  "GET /api/platform-collections": { links: [], room_left: 46 },
  ...extra,
});

function dragData(type: string, value: unknown) {
  const store: Record<string, string> = { [type]: JSON.stringify(value) };
  return {
    setData: (t: string, v: string) => { store[t] = v; },
    getData: (t: string) => store[t] ?? "",
    get types() { return Object.keys(store); },
    effectAllowed: "", dropEffect: "",
  };
}

beforeEach(() => {
  window.location.hash = "";
  vi.stubGlobal("EventSource", FakeEventSource);
});

// ---------- spaces and folders ----------

test("a space shows its top collections; opening one shows what's inside first, then its saves", async () => {
  const calls = fakeBackend(base({
    "GET /api/library/items": { total: 1, offset: 0, items: [libraryItem({ id: 7, title: "Periodic table song", collections: [{ id: 1, name: "Study", origin: "mine", source: "user", confidence: null }] })] },
  }));
  const { rerender } = render(<CollectionsPage />);
  const top = await screen.findByRole("list", { name: "Your collections" });
  expect(within(top).getAllByRole("link").map((a) => a.getAttribute("aria-label"))).toEqual(["Study", "Want to go", "Music"]);
  expect(within(top).getByText("3 saves · 2 inside")).toBeInTheDocument(); // Study, with Chemistry inside it
  expect(screen.getByRole("tab", { name: /My saves/ })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("4 of 50 collections used in My saves")).toBeInTheDocument();

  rerender(<CollectionsPage selection="1" />);
  const inside = await screen.findByRole("list", { name: "Collections in Study" });
  expect(within(inside).getByRole("link", { name: "Chemistry" })).toHaveAttribute("href", "#/collections/4");
  const savesList = await screen.findByRole("list", { name: "Saves in Study" });
  expect(within(savesList).getByText("Periodic table song")).toBeInTheDocument();
  // Folders come before saves on the page.
  expect(inside.compareDocumentPosition(savesList) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  // Only this collection's own saves are asked for, not those of the ones inside it.
  expect(calls.find((c) => c.url.startsWith("/api/library/items"))?.url).toContain("collection_id=1&include_sub=false");

  const path = screen.getByRole("navigation", { name: "Path" });
  expect(within(path).getAllByRole("link").map((a) => a.textContent)).toEqual(["My saves", "Study"]);
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(window.location.hash).toBe("#/collections");
});

test("search within the open collection keeps the server query scoped to its own saves", async () => {
  const calls = fakeBackend(base({
    "GET /api/library/items": (_body: unknown, url: string) => {
      const query = new URL(url, "http://localhost").searchParams;
      const matching = query.get("q") === "atoms";
      const item = libraryItem({ id: matching ? 8 : 7, title: matching ? "Atoms explained" : "Periodic table song" });
      return { total: 1, offset: 0, items: [item] };
    },
  }));
  render(<CollectionsPage selection="1" />);
  expect(await screen.findByText("Periodic table song")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox", { name: "Search saves in this collection" }), { target: { value: "atoms" } });
  expect(await screen.findByText("Atoms explained")).toBeInTheDocument();
  expect(screen.queryByText("Periodic table song")).toBeNull();
  const request = calls.find(call => call.url.includes("q=atoms"));
  expect(request?.url).toContain("collection_id=1");
  expect(request?.url).toContain("include_sub=false");
});

test("a new collection is made where you are: in the open collection, or in the chosen space", async () => {
  window.location.hash = "#/collections?space=2";
  const calls = fakeBackend(base({ "POST /api/collections": { ...overview(), created_id: 9 } }));
  const { rerender } = render(<CollectionsPage />);
  expect(await screen.findByRole("link", { name: "Decks" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Music" })).not.toBeInTheDocument(); // that's in the other space
  fireEvent.click(screen.getByRole("button", { name: /New collection/ }));
  fireEvent.change(screen.getByLabelText("New collection name"), { target: { value: "Clients" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Clients", parent_id: null, space_id: 2 }));

  window.location.hash = "#/collections/1";
  rerender(<CollectionsPage selection="1" />);
  fireEvent.click(await screen.findByRole("button", { name: /New collection/ }));
  fireEvent.change(screen.getByLabelText("New collection name"), { target: { value: "Physics" } });
  fireEvent.click(screen.getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "POST")[1]?.body).toEqual({ name: "Physics", parent_id: 1, space_id: 1 }));
});

test("pick collections with the boxes and Shift, then move them together", async () => {
  const calls = fakeBackend(base({ "POST /api/collections/bulk": { ...overview(), changed: 2 } }));
  render(<CollectionsPage />);
  fireEvent.click(await screen.findByRole("checkbox", { name: "Pick Study" }));
  fireEvent.click(screen.getByRole("link", { name: "Music" }), { shiftKey: true }); // Study, Want to go and Music
  const bar = screen.getByRole("toolbar", { name: "Picked collections" });
  expect(bar).toHaveTextContent("3 collections picked");
  expect(window.location.hash).toBe(""); // picking doesn't open anything
  fireEvent.click(screen.getByRole("checkbox", { name: "Pick Want to go" })); // unpick the middle one

  fireEvent.click(within(bar).getByRole("button", { name: "Move to…" }));
  const dialog = await screen.findByRole("dialog", { name: "Move 2 collections" });
  const options = within(dialog).getAllByRole("option").map((o) => o.textContent?.trim());
  expect(options).toEqual(["My saves (top of this space)", "Want to go", "Work (top of this space)", "Decks"]); // not into themselves
  fireEvent.change(within(dialog).getByLabelText("Put in"), { target: { value: "in:5" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Move" }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/collections/bulk")?.body).toEqual({ ids: [1, 3], action: "move", parent_id: 5 }));
});

test("drag a collection onto another, onto the path, or onto a space tab", async () => {
  const calls = fakeBackend(base({
    "POST /api/collections/bulk": { ...overview(), changed: 1 },
    "GET /api/library/items": { total: 0, offset: 0, items: [] },
  }));
  const { rerender } = render(<CollectionsPage />);
  const music = await screen.findByTestId("folder-3");
  const study = screen.getByTestId("folder-1");
  const dataTransfer = dragData("application/x-keptwise-collection", { ids: [3] });
  fireEvent.dragStart(music, { dataTransfer });
  fireEvent.dragOver(study, { dataTransfer });
  fireEvent.drop(study, { dataTransfer });
  await waitFor(() => expect(calls.find((c) => c.url === "/api/collections/bulk")?.body).toEqual({ ids: [3], action: "move", parent_id: 1 }));

  fireEvent.drop(screen.getByRole("tab", { name: /Work/ }), { dataTransfer });
  await waitFor(() => expect(calls.filter((c) => c.url === "/api/collections/bulk")[1]?.body).toEqual({ ids: [3], action: "move", parent_id: null, space_id: 2 }));

  // Inside Study, drop Chemistry on the first step of the path to move it back out.
  rerender(<CollectionsPage selection="1" />);
  await screen.findByTestId("folder-4");
  const out = dragData("application/x-keptwise-collection", { ids: [4] });
  fireEvent.drop(within(screen.getByRole("navigation", { name: "Path" })).getByText("My saves"), { dataTransfer: out });
  await waitFor(() => expect(calls.filter((c) => c.url === "/api/collections/bulk")[2]?.body).toEqual({ ids: [4], action: "move", parent_id: null, space_id: 1 }));
});

test("dropping a save on a collection files it; several picked saves are added together", async () => {
  const calls = fakeBackend(base({
    "POST /api/items/1/move": card({}),
    "POST /api/items/bulk": { changed: 2, skipped_full: 1, items: [] },
  }));
  render(<CollectionsPage />);
  const music = await screen.findByTestId("folder-3");
  const one = dragData("application/x-saves-item", { itemId: 1, fromId: null });
  fireEvent.dragOver(music, { dataTransfer: one });
  fireEvent.drop(music, { dataTransfer: one });
  await waitFor(() => expect(calls.find((c) => c.url === "/api/items/1/move")?.body).toEqual({ from_id: null, to_id: 3 }));

  const many = dragData("application/x-saves-item", { itemId: 1, fromId: null, itemIds: [1, 2, 5] });
  fireEvent.drop(music, { dataTransfer: many });
  await waitFor(() =>
    expect(calls.find((c) => c.url === "/api/items/bulk")?.body).toEqual({ item_ids: [1, 2, 5], action: "add_to", collection_id: 3, from_id: null }),
  );
});

test("right-click a collection: rename it, add one inside, then delete it after asking", async () => {
  const calls = fakeBackend(base({
    "PATCH /api/collections/3": overview(),
    "DELETE /api/collections/3": overview(),
    "POST /api/collections": { ...overview(), created_id: 9 },
  }));
  render(<CollectionsPage />);
  const music = await screen.findByTestId("folder-3");

  fireEvent.contextMenu(music, { clientX: 50, clientY: 60 });
  const menu = await screen.findByRole("menu", { name: "Music" });
  fireEvent.click(within(menu).getByRole("menuitem", { name: "Rename…" }));
  const rename = await screen.findByRole("dialog", { name: "Rename collection" });
  fireEvent.change(within(rename).getByLabelText("Name"), { target: { value: "Songs" } });
  fireEvent.click(within(rename).getByRole("button", { name: "Save" }));
  await waitFor(() => expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({ name: "Songs" }));

  fireEvent.contextMenu(music, { clientX: 50, clientY: 60 });
  fireEvent.click(within(await screen.findByRole("menu", { name: "Music" })).getByRole("menuitem", { name: "New collection inside…" }));
  const inside = await screen.findByRole("dialog", { name: "New collection in “Music”" });
  fireEvent.change(within(inside).getByLabelText("Name"), { target: { value: "Playlists" } });
  fireEvent.click(within(inside).getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Playlists", parent_id: 3 }));

  fireEvent.contextMenu(music, { clientX: 50, clientY: 60 });
  fireEvent.click(within(await screen.findByRole("menu", { name: "Music" })).getByRole("menuitem", { name: "Delete…" }));
  const sure = await screen.findByRole("dialog", { name: "Delete “Music”?" });
  expect(calls.some((c) => c.method === "DELETE")).toBe(false); // nothing yet: it asks first
  fireEvent.click(within(sure).getByRole("button", { name: "Delete" }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/collections/3")).toBe(true));
});

test("spaces: add one, and the full one says so", async () => {
  const full = Array.from({ length: 50 }, (_, i) => collection(i + 10, `Topic ${i + 1}`));
  const calls = fakeBackend(base({
    "GET /api/collections": { ...overview(), collections: full },
    "POST /api/spaces": { ...overview(), created_space: 3 },
  }));
  render(<CollectionsPage />);
  expect(await screen.findByText("50 of 50 collections used in My saves")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /New collection/ })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Add a space" }));
  const dialog = await screen.findByRole("dialog", { name: "New space" });
  fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "Trips" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Add" }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/spaces")?.body).toEqual({ name: "Trips" }));
  await waitFor(() => expect(window.location.hash).toBe("#/collections?space=3"));
});

// ---------- the three ways to organise ----------

test("the Collections page has no AI buttons: the AI's work is on the Sort page", async () => {
  fakeBackend(base({ "GET /api/collections": overview({ processed: 5, unsorted: 2, waiting: 20 }) }));
  render(<CollectionsPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Organise" }));
  expect(await screen.findByRole("button", { name: /Organise by hand/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Bring from your platform/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Let the AI organise/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /AI sort/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: /Needs review/ })).not.toBeInTheDocument();
  expect(screen.getByRole("tab", { name: /Unsorted/ })).toHaveTextContent("2");
});

test("how the AI sorts is chosen here: each choice and the user's rules are saved", async () => {
  const calls = fakeBackend(base());
  render(<CollectionSortOptions collections={tree as never} />);
  expect(await screen.findByText(/never makes new ones/)).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("radio", { name: "Just one" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(1));
  expect((calls.find((c) => c.method === "PATCH")?.body as { max_collections: number }).max_collections).toBe(1);

  fireEvent.click(screen.getByRole("radio", { name: "Clear only" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(2));
  expect((calls.filter((c) => c.method === "PATCH")[1].body as { review_below: number }).review_below).toBe(0.9);

  fireEvent.change(screen.getByLabelText("Rule type"), { target: { value: "text" } });
  fireEvent.change(screen.getByLabelText("Word or phrase"), { target: { value: "Japan" } });
  fireEvent.change(screen.getByLabelText("Collection for this rule"), { target: { value: "Want to go" } });
  fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(3));
  expect((calls.filter((c) => c.method === "PATCH")[2].body as { rules: unknown[] }).rules).toEqual([
    { field: "text", value: "Japan", collection: "Want to go", tag: "" },
  ]);

  // A rule can add a tag instead of filing the save.
  fireEvent.change(screen.getByLabelText("Rule type"), { target: { value: "author" } });
  fireEvent.change(screen.getByLabelText("Creator name"), { target: { value: "chef.sam" } });
  fireEvent.change(screen.getByLabelText("What the rule does"), { target: { value: "tag" } });
  fireEvent.change(screen.getByLabelText("Tag for this rule"), { target: { value: "#cooking" } });
  fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
  await waitFor(() => expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(4));
  expect((calls.filter((c) => c.method === "PATCH")[3].body as { rules: unknown[] }).rules[1]).toEqual({
    field: "author", value: "chef.sam", collection: "", tag: "cooking",
  });
});

test("the Settings section keeps what the notes contain, and whether the AI looks at pictures", async () => {
  const calls = fakeBackend(base());
  render(<SortingSettings />);
  const pictures = await screen.findByRole("switch", { name: /Use pictures as well/ });
  expect(screen.getByRole("heading", { name: "Notes" })).toBeInTheDocument();
  expect(pictures).toBeChecked(); // on unless switched off
  // How the AI picks collections and tags is on the Sort page; unsaving has no setting.
  expect(screen.queryByRole("radio", { name: "Just one" })).not.toBeInTheDocument();
  expect(screen.queryByText(/Safe to unsave/)).not.toBeInTheDocument();
  expect(screen.queryByRole("radio", { name: "Up to 10" })).not.toBeInTheDocument();
  fireEvent.click(pictures);
  await waitFor(() => expect((calls.find((c) => c.method === "PATCH")?.body as { look_at_pictures: boolean }).look_at_pictures).toBe(false));
});

test("Unsorted: accept where the AI thinks a save goes, or choose another", async () => {
  const unsure = card({ id: 13, title: "4k 60fps Video Clip", collections: [], suggestions: [{ name: "Music", confidence: 0.75 }] });
  const calls = fakeBackend(base({
    "GET /api/collections": overview({ unsorted: 4, processed: 20, waiting: 0 }),
    "GET /api/library?view=unsorted": [unsure],
    "POST /api/review/13/accept": card({ id: 13 }),
  }));
  render(<CollectionsPage selection="unsorted" />);
  expect(await screen.findByRole("heading", { name: "Unsorted" })).toBeInTheDocument();
  const row = await screen.findByTestId("unsorted-13");
  fireEvent.click(within(row).getByRole("button", { name: "Accept" }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/review/13/accept")?.body).toEqual({}));
  fireEvent.click(within(row).getByRole("button", { name: "Choose another" }));
  const picker = await screen.findByRole("dialog", { name: /Choose a collection/ });
  fireEvent.change(within(picker).getByLabelText("Find a collection"), { target: { value: "chem" } });
  fireEvent.click(within(picker).getByRole("button", { name: /Chemistry/ }));
  await waitFor(() => expect(calls.filter((c) => c.url === "/api/review/13/accept")[1]?.body).toEqual({ collection_id: 4 }));

  // The old Needs review address lands here too.
  render(<CollectionsPage selection="review" />);
  expect((await screen.findAllByRole("heading", { name: "Unsorted" })).length).toBe(2);
});

test("Unsorted selects ranges and sends only the selected saves to bulk actions", async () => {
  const rows = [13, 14, 15, 16].map(id => card({ id, title: "Video " + id, collections: [] }));
  const calls = fakeBackend(base({
    "GET /api/library?view=unsorted": rows,
    "POST /api/items/bulk": { changed: 4, skipped_full: 0, items: [] },
    "POST /api/sorting/resort": httpError(409, { code: "confirm_cost", detail: "About three requests." }),
  }));
  render(<CollectionsPage selection="unsorted" />);
  const first = await screen.findByRole("link", { name: "Video 13" });
  const third = screen.getByRole("checkbox", { name: "Select Video 15" });
  fireEvent.click(first, { ctrlKey: true });
  fireEvent.click(third, { shiftKey: true });
  const toolbar = screen.getByRole("toolbar", { name: "Selected saves" });
  expect(toolbar).toHaveTextContent("3 selected");
  fireEvent.click(within(toolbar).getByRole("button", { name: "Re-sort selected" }));
  const dialog = await screen.findByRole("dialog", { name: "Use cloud AI to re-sort?" });
  expect(calls.filter(c => c.url === "/api/sorting/resort").map(c => c.body)).toEqual([
    { which: "unsorted", keep_manual: true, confirm_cost: false, item_ids: [13, 14, 15] },
  ]);
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  fireEvent.keyDown(third, { key: "a", ctrlKey: true });
  expect(toolbar).toHaveTextContent("4 selected");
  fireEvent.change(within(toolbar).getByRole("combobox", { name: "Move the selected saves into a collection" }), { target: { value: "4" } });
  await waitFor(() => expect(calls.find(c => c.url === "/api/items/bulk")?.body).toEqual({
    action: "add_to", collection_id: 4, item_ids: [13, 14, 15, 16],
  }));
  fireEvent.keyDown(third, { key: "Escape" });
  expect(screen.queryByRole("toolbar", { name: "Selected saves" })).toBeNull();
});

test("bring from your platform: one button makes them here, and it says what happens next", async () => {
  const link = (name: string, platform: string, extra: Record<string, unknown> = {}) => ({
    platform, platform_name: platform === "tiktok" ? "TikTok" : "YouTube", name, count: platform === "tiktok" ? 0 : 4,
    membership_known: platform !== "tiktok", collection_id: null, collection_name: null, mode: "auto", filed: 0, ...extra,
  });
  const links = { links: [link("Recipes", "youtube"), link("gym", "tiktok"), link("Music", "tiktok", { collection_id: 3, collection_name: "Music" })], room_left: 46 };
  const calls = fakeBackend(base({
    "GET /api/platform-collections": links,
    "POST /api/platform-collections/transfer": { ...links, linked: 2, made: 1, filed: 4, no_room: 0 },
  }));
  render(<CollectionsPage selection="links" />);
  expect(await screen.findByText(/TikTok may export folder names/)).toBeInTheDocument();
  expect(screen.getByText("Manage collection links (1)")).toBeInTheDocument();
  expect(screen.queryByLabelText("Destination for TikTok gym")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Import 2 collections" }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/platform-collections/transfer")?.body).toEqual({ space_id: 1, parent_id: null }));
  expect(await screen.findByText("Made 1 collection in My saves, 1 already existed and was kept, 4 saves put in them.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Go to Sort" }));
  expect(window.location.hash).toBe("#/transcripts");
});

test("sets a TikTok default and maps an imported playlist independently", async () => {
  const links = {
    links: [{
      platform: "youtube", platform_name: "YouTube", name: "Recipes", count: 4,
      membership_known: true, collection_id: null, collection_name: null, mode: "auto", filed: 0,
    }],
    import_destinations: [{ platform: "tiktok", platform_name: "TikTok", collection_id: null }],
    room_left: 46,
  };
  const calls = fakeBackend(base({
    "GET /api/platform-collections": links,
    "PUT /api/platform-collections/default": links,
    "PUT /api/platform-collections": { ...links, filed: 4 },
  }));
  render(<CollectionsPage selection="links" />);
  const destination = await screen.findByLabelText("TikTok");
  await waitFor(() => expect(destination).not.toBeDisabled());
  fireEvent.change(destination, { target: { value: "3" } });
  expect(await screen.findByText("TikTok import destination updated.")).toBeInTheDocument();
  expect(calls.find((call) => call.url.endsWith("/default"))?.body).toEqual({ platform: "tiktok", collection_id: 3 });
  fireEvent.click(screen.getByText("Manage collection links (1)"));
  fireEvent.change(screen.getByLabelText("Destination for YouTube Recipes"), { target: { value: "3" } });
  expect(await screen.findByText("Filed 4 saves.")).toBeInTheDocument();
  expect(calls.find((call) => call.url === "/api/platform-collections" && call.method === "PUT")?.body)
    .toEqual({ platform: "youtube", name: "Recipes", collection_id: 3, mode: "auto" });
});
