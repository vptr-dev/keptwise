// Collections (#/collections, #/collections/12, #/collections/review,
// #/collections/unsorted, #/collections/links).
//
// Collections work like folders: they sit in spaces (the tabs at the top) and
// inside each other. Folders are always shown first; click one to open it,
// like in Windows Explorer, with the path above to go back. Tick the boxes
// (or Ctrl / Shift click) to pick several collections or saves and move them
// together; drag a collection onto another to put it inside; right-click for
// everything else. Needs review and Not in a collection are tabs at the end
// of the spaces row. The three ways to organise (AI, by hand, from your
// platforms) fold away behind the Organise button at the top.
import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent, type CSSProperties, type MouseEvent, type ReactNode } from "react";

import { useContextMenu, type MenuItem } from "../components/ContextMenu";
import { useDialog, type Ask } from "../components/Dialog";
import JobCard from "../components/JobCard";
import { toast } from "../components/Toasts";
import { icons } from "../components/icons";
import { Button, Notice, inputClass } from "../components/ui";
import LibraryCard from "../features/library/LibraryCard";
import { selectionMenuItems } from "../features/library/saveMenu";
import { DEFAULT_QUERY, libraryApi, type LibraryItem } from "../features/library/libraryApi";
import BulkBar from "../features/organize/BulkBar";
import CollectionHeader from "../features/organize/CollectionHeader";
import FolderIcon from "../features/organize/FolderIcon";
import OrganiseChoices from "../features/organize/OrganiseChoices";
import { collectionMenuItems, moveTargets, targetOf } from "../features/organize/menus";
import {
  COLLECTION_DRAG,
  COLOR_DOTS,
  ITEMS_DRAG,
  announceChange,
  draggedIds,
  onOrganizeChange,
  organizeApi,
  readItemsDrag,
  type ItemsDrag,
} from "../features/organize/organizeApi";
import ItemCard from "../features/sorting/ItemCard";
import ReviewActions from "../features/sorting/ReviewActions";
import {
  COLLECTION_LIMIT,
  COLLECTIONS_PER_SAVE,
  sortingApi,
  type Collection,
  type CollectionsOverview,
  type ItemCard as Item,
  type NotesOverview,
  type Space,
  type View,
} from "../features/sorting/sortingApi";
import { errorCode, errorText } from "../lib/api";
import { isActive, onJobUpdate, useJobs, type Job } from "../lib/jobs";
import { navigate, useRoute } from "../lib/router";
import { Tip } from "../lib/tips";

type Pending = { message: string; go: () => void };
type Selection = View | { type: "links" } | { type: "overview" };

const AI_JOBS = ["notes", "sort", "tags"];

function selectionFrom(selection: string | null): Selection {
  if (selection && /^\d+$/.test(selection)) return { type: "collection", id: Number(selection) };
  if (selection === "review" || selection === "unsorted" || selection === "all" || selection === "links")
    return { type: selection };
  return { type: "overview" };
}

/** The collections being dragged (one, or every picked one). */
function readCollectionsDrag(data: DataTransfer): number[] | null {
  try {
    const ids = (JSON.parse(data.getData(COLLECTION_DRAG)) as { ids: number[] }).ids;
    return Array.isArray(ids) && ids.length ? ids : null;
  } catch {
    return null;
  }
}

/** Tick one, or with Shift everything between the last one ticked and this one. */
function pickFrom(order: number[], picked: number[], last: number | null, id: number, shift: boolean): number[] {
  if (shift && last !== null && order.includes(last)) {
    const [from, to] = [order.indexOf(last), order.indexOf(id)].sort((a, b) => a - b);
    return [...new Set([...picked, ...order.slice(from, to + 1)])];
  }
  return picked.includes(id) ? picked.filter((p) => p !== id) : [...picked, id];
}

export default function CollectionsPage({ selection = null }: { selection?: string | null }) {
  const jobs = useJobs();
  const route = useRoute();
  const [overview, setOverview] = useState<CollectionsOverview | null>(null);
  const [notes, setNotes] = useState<NotesOverview | null>(null);
  const [items, setItems] = useState<Item[]>([]); // Needs review / Not in a collection
  const [saves, setSaves] = useState<{ total: number; items: LibraryItem[] } | null>(null); // the open collection's own saves
  const [started, setStarted] = useState<Job | null>(null);
  const [problem, setProblem] = useState<{ text: string; code: string | null } | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const [keepManual, setKeepManual] = useState(true);
  const [newName, setNewName] = useState("");
  const [adding, setAdding] = useState(false);
  const [find, setFind] = useState("");
  const [details, setDetails] = useState(false);
  const [organise, setOrganise] = useState(selection === "links");
  useEffect(() => {
    if (selection === "links") setOrganise(true);
  }, [selection]);
  const [pickedFolders, setPickedFolders] = useState<number[]>([]);
  const [pickedSaves, setPickedSaves] = useState<number[]>([]);
  const lastFolder = useRef<number | null>(null);
  const lastSave = useRef<number | null>(null);
  const lastDepth = useRef(-1);
  const [ask, dialog] = useDialog();
  const [openMenu, menu] = useContextMenu();

  const view = selectionFrom(selection);
  const viewKey = view.type === "collection" ? `c${view.id}` : view.type;
  const openId = view.type === "collection" ? view.id : null;

  const refreshLists = useCallback(() => {
    sortingApi.collections().then(setOverview).catch((e) => setProblem({ text: errorText(e), code: null }));
    sortingApi.overview().then(setNotes).catch(() => undefined);
  }, []);
  useEffect(refreshLists, [refreshLists]);

  const refreshItems = useCallback(() => {
    if (viewKey === "review" || viewKey === "unsorted" || viewKey === "all") {
      sortingApi.library({ type: viewKey } as View).then(setItems).catch((e) => setProblem({ text: errorText(e), code: null }));
    } else if (openId !== null) {
      libraryApi
        .items({ ...DEFAULT_QUERY, collection_id: String(openId) }, 0, false)
        .then((page) => setSaves({ total: page.total, items: page.items }))
        .catch((e) => setProblem({ text: errorText(e), code: null }));
    }
  }, [viewKey, openId]);
  useEffect(() => {
    setItems([]);
    setSaves(null);
    setPickedFolders([]);
    setPickedSaves([]);
    setFind("");
    setAdding(false);
    setDetails(false);
    refreshItems();
  }, [refreshItems]);
  useEffect(
    () =>
      onOrganizeChange(() => {
        refreshLists();
        refreshItems();
      }),
    [refreshLists, refreshItems],
  );

  // While AI jobs run, every finished save shows up straight away.
  useEffect(() => {
    let last = -1;
    return onJobUpdate((job) => {
      if (!AI_JOBS.includes(job.kind)) return;
      if (job.progress !== last || !isActive(job)) {
        last = job.progress;
        refreshLists();
        refreshItems();
      }
    });
  }, [refreshLists, refreshItems]);

  const aiJobs = jobs.filter((job) => AI_JOBS.includes(job.kind));
  const running = aiJobs.find(isActive);
  const currentId = running?.id ?? Math.max(started?.id ?? 0, aiJobs[0]?.id ?? 0);
  const current = aiJobs.find((job) => job.id === currentId) ?? started ?? undefined;
  const busy = running !== undefined;

  async function run(task: () => Promise<Job>, retry: () => void) {
    setProblem(null);
    setPending(null);
    try {
      setStarted(await task());
    } catch (e) {
      if (errorCode(e) === "confirm_cost") setPending({ message: errorText(e), go: retry });
      else setProblem({ text: errorText(e), code: errorCode(e) });
    }
  }
  const startSort = (which: "all" | "review" | "unsorted", confirm = false) =>
    run(() => sortingApi.resort(which, keepManual, confirm), () => startSort(which, true));

  async function act(task: () => Promise<unknown>) {
    setProblem(null);
    try {
      await task();
    } catch (e) {
      setProblem({ text: errorText(e), code: errorCode(e) });
    }
    announceChange();
  }

  // ---------- where we are ----------

  const collections = overview?.collections ?? [];
  const spaces = overview?.spaces ?? [];
  const limit = overview?.limit ?? COLLECTION_LIMIT;
  const counts = overview?.counts;
  const opened = openId !== null ? collections.find((c) => c.id === openId) : undefined;
  const wantedSpace = Number(route.query.get("space")) || null;
  const space = spaces.find((s) => s.id === (opened?.space_id ?? wantedSpace)) ?? spaces[0];
  const inSpace = collections.filter((c) => c.space_id === space?.id);
  const folders = inSpace.filter((c) => c.parent_id === (opened?.id ?? null));
  const wanted = find.trim().toLowerCase();
  // Typing in the find box looks through the whole space, at any depth.
  const shownFolders = wanted
    ? inSpace.filter((c) => c.name.toLowerCase().includes(wanted) || (c.description ?? "").toLowerCase().includes(wanted))
    : folders;
  const path: Collection[] = [];
  for (let at = opened; at; at = collections.find((c) => c.id === at?.parent_id)) path.unshift(at);
  const waiting = notes?.counts.waiting ?? 0;
  const explorer = view.type === "overview" || view.type === "collection" || view.type === "links";
  const spaceHref = (id: number | undefined) => `/collections${id && id !== spaces[0]?.id ? `?space=${id}` : ""}`;
  const upHref = path.length > 1 ? `/collections/${path[path.length - 2].id}` : spaceHref(space?.id);

  // Slide in from the right when going deeper, from the left when going back.
  const depthNow = opened ? opened.depth : -1;
  const slide = depthNow >= lastDepth.current ? "kw-in-right" : "kw-in-left";
  useEffect(() => {
    lastDepth.current = depthNow;
  }, [depthNow, viewKey]);

  // Esc clears what's picked; Alt+Left (or Backspace) goes up a level.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable]")) return;
      if (event.key === "Escape" && (pickedFolders.length || pickedSaves.length)) {
        setPickedFolders([]);
        setPickedSaves([]);
      } else if (opened && ((event.altKey && event.key === "ArrowLeft") || event.key === "Backspace")) {
        event.preventDefault();
        navigate(upHref);
      } else if (event.ctrlKey && event.key.toLowerCase() === "a" && explorer && !wanted) {
        event.preventDefault();
        setPickedFolders(folders.map((c) => c.id));
        setPickedSaves((saves?.items ?? []).map((i) => i.id));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- doing things ----------

  function create(event: FormEvent) {
    event.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setNewName("");
    setAdding(false);
    act(() => organizeApi.createCollection(name, opened?.id ?? null, space?.id).then(() => toast(`Added “${name}”.`)));
  }

  /** One dropped save is moved; several picked ones are added together. */
  function fileDropped(drag: ItemsDrag, collection: Collection) {
    const ids = draggedIds(drag);
    if (ids.length <= 1) {
      if (drag.fromId === collection.id) return;
      act(() => sortingApi.move(drag.itemId, drag.fromId, collection.id).then(() => toast(`Filed in “${collection.name}”.`)));
      return;
    }
    act(async () => {
      const done = await organizeApi.bulk({ item_ids: ids, action: drag.fromId ? "move_to" : "add_to", collection_id: collection.id, from_id: drag.fromId });
      const skipped = done.skipped_full ? ` ${done.skipped_full} were already in ${COLLECTIONS_PER_SAVE} collections.` : "";
      toast(`${drag.fromId ? "Moved" : "Added"} ${done.changed} saves to “${collection.name}”.${skipped}`);
      setPickedSaves([]);
    });
  }

  /** Put the dragged collections inside one (or at the top of a space). */
  function moveCollections(ids: number[], target: { parent_id: number | null; space_id?: number }, where: string) {
    const moving = ids.filter((id) => id !== target.parent_id);
    if (!moving.length) return;
    act(async () => {
      await organizeApi.bulkCollections({ ids: moving, action: "move", ...target });
      toast(`Moved ${moving.length === 1 ? `“${collections.find((c) => c.id === moving[0])?.name}”` : `${moving.length} collections`} ${where}.`);
      setPickedFolders([]);
    });
  }

  /** What a drop on a collection, a step of the path, or a space tab does. */
  function dropOn(event: DragEvent, target: { collection?: Collection; space?: Space }) {
    event.preventDefault();
    const dragged = readCollectionsDrag(event.dataTransfer);
    if (dragged) {
      if (target.collection) moveCollections(dragged, { parent_id: target.collection.id }, `into “${target.collection.name}”`);
      else if (target.space) moveCollections(dragged, { parent_id: null, space_id: target.space.id }, `to ${target.space.name}`);
      return;
    }
    const drag = readItemsDrag(event.dataTransfer);
    if (drag && target.collection) fileDropped(drag, target.collection);
  }

  function pickFolder(collection: Collection, event: MouseEvent) {
    const order = shownFolders.map((c) => c.id);
    const [last, shift] = [lastFolder.current, event.shiftKey];
    setPickedFolders((old) => pickFrom(order, old, last, collection.id, shift));
    lastFolder.current = collection.id;
  }
  function pickSave(item: LibraryItem, event: MouseEvent) {
    const order = (saves?.items ?? []).map((i) => i.id);
    const [last, shift] = [lastSave.current, event.shiftKey];
    setPickedSaves((old) => pickFrom(order, old, last, item.id, shift));
    lastSave.current = item.id;
  }

  async function moveFolders() {
    const moving = collections.filter((c) => pickedFolders.includes(c.id));
    const where = await ask.pick({
      title: `Move ${moving.length === 1 ? `“${moving[0].name}”` : `${moving.length} collections`}`,
      label: "Put in",
      options: moveTargets(moving, collections, spaces),
      confirm: "Move",
      hint: "Everything inside them moves too.",
    });
    if (where) moveCollections(pickedFolders, targetOf(where), "there");
  }
  async function deleteFolders() {
    const sure = await ask.confirm({
      title: `Delete ${pickedFolders.length} collection${pickedFolders.length === 1 ? "" : "s"}?`,
      body: "Their saves stay in the app; they just won't be in these collections any more. Collections inside them move up a level.",
      confirm: "Delete",
      danger: true,
    });
    if (!sure) return;
    const ids = pickedFolders;
    setPickedFolders([]);
    act(async () => {
      await organizeApi.bulkCollections({ ids, action: "delete" });
      toast(`Deleted ${ids.length} collection${ids.length === 1 ? "" : "s"}.`);
    });
  }

  async function loadMore() {
    if (!saves || openId === null) return;
    try {
      const page = await libraryApi.items({ ...DEFAULT_QUERY, collection_id: String(openId) }, saves.items.length, false);
      setSaves({ total: page.total, items: [...saves.items, ...page.items] });
    } catch (e) {
      setProblem({ text: errorText(e), code: null });
    }
  }

  const updateSave = (changed: LibraryItem) =>
    setSaves((old) => old && { ...old, items: old.items.map((i) => (i.id === changed.id ? changed : i)) });
  const roomHere = (space ? limit - inSpace.length : 0) > 0;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-5 px-8 py-8">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Collections</h1>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              Folders for your saves. Put collections inside collections, and keep separate areas in spaces.
            </p>
          </div>
          <Button variant={organise ? "primary" : "secondary"} aria-expanded={organise} onClick={() => setOrganise(!organise)}>
            <span className="h-4 w-4">{icons.sparkle}</span>
            Organise
            <span className={`h-4 w-4 transition-transform ${organise ? "rotate-180" : ""}`}>{icons.down}</span>
          </Button>
        </header>

        <SpaceTabs
          spaces={spaces}
          current={explorer ? space?.id : undefined}
          limit={overview?.space_limit ?? 8}
          ask={ask}
          act={act}
          hrefOf={spaceHref}
          onDrop={(event, target) => dropOn(event, { space: target })}
          view={view.type === "review" || view.type === "unsorted" ? view.type : null}
          review={counts?.review ?? 0}
          unsorted={counts?.unsorted ?? 0}
        />

        {organise && (
          <div className="kw-rise">
            <OrganiseChoices
              collections={collections}
              counts={counts}
              notes={notes}
              busy={busy}
              spaceId={space?.id}
              spaceName={space?.name ?? "this space"}
              inside={opened}
              initial={view.type === "links" ? "platforms" : null}
              keepManual={keepManual}
              onKeepManual={setKeepManual}
              onSort={startSort}
            />
          </div>
        )}

        {pending && (
          <Notice tone="warning" onClose={() => setPending(null)}>
            <p>{pending.message}</p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={pending.go}>
                Yes, go ahead
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setPending(null)}>
                Cancel
              </Button>
            </div>
          </Notice>
        )}
        {problem && (
          <Notice tone="error" onClose={() => setProblem(null)}>
            <p>{problem.text}</p>
            {problem.code && ["model_missing", "missing_key", "missing_model", "unreachable"].includes(problem.code) && (
              <div className="mt-3">
                <Button size="sm" variant="secondary" onClick={() => navigate("/settings?section=ai")}>
                  Open AI settings
                </Button>
              </div>
            )}
          </Notice>
        )}
        {current && <JobCard job={current} name={current.kind === "sort" ? "AI sort" : current.kind === "tags" ? "AI tags job" : "AI notes job"} />}

        {explorer && (
          <section className="space-y-4" aria-label="Collections in this space">
            <Tip id="collections-explorer">
              Click a collection to open it; the path above takes you back. <b>Drag</b> a collection onto another to put it
              inside. Tick the boxes, or Ctrl-click and Shift-click, to pick several. <b>Right-click</b> for everything else.
            </Tip>

            {/* The path, like an address bar, and what you can do here. */}
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                aria-label="Back"
                title="Up a level (Alt+Left)"
                disabled={!opened}
                onClick={() => navigate(upHref)}
                className="flex h-8 w-8 items-center justify-center rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-100 disabled:opacity-30 dark:hover:bg-zinc-800"
              >
                {icons.back}
              </button>
              <nav aria-label="Path" className="flex min-w-0 flex-1 flex-wrap items-center gap-0.5 text-sm">
                <Crumb
                  href={`#${spaceHref(space?.id)}`}
                  current={!opened}
                  onDrop={(event) => space && dropOn(event, { space })}
                >
                  {space?.name ?? "…"}
                </Crumb>
                {path.map((step, index) => (
                  <span key={step.id} className="flex items-center gap-0.5">
                    <span className="h-3.5 w-3.5 -rotate-90 text-zinc-400" aria-hidden="true">
                      {icons.down}
                    </span>
                    <Crumb href={`#/collections/${step.id}`} current={index === path.length - 1} onDrop={(event) => dropOn(event, { collection: step })}>
                      {step.name}
                    </Crumb>
                  </span>
                ))}
              </nav>
              <input
                type="search"
                className={`${inputClass} !w-44 py-1.5`}
                placeholder={`Find in ${space?.name ?? "this space"}`}
                aria-label="Find a collection"
                value={find}
                onChange={(e) => setFind(e.target.value)}
              />
              {adding ? (
                <form onSubmit={create} className="flex gap-1.5">
                  <input
                    className={`${inputClass} !w-44 py-1.5`}
                    placeholder={opened ? `New one in ${opened.name}` : "New collection"}
                    aria-label="New collection name"
                    maxLength={80}
                    autoFocus
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => e.key === "Escape" && setAdding(false)}
                  />
                  <Button type="submit" disabled={!newName.trim()}>
                    Add
                  </Button>
                </form>
              ) : (
                <Button
                  onClick={() => setAdding(true)}
                  disabled={!roomHere}
                  title={roomHere ? undefined : `This space has ${limit} collections, the most it can hold`}
                >
                  <span className="h-4 w-4">{icons.plus}</span>
                  New collection
                </Button>
              )}
            </div>

            {opened && (
              <div className="flex flex-wrap items-center gap-3">
                <FolderIcon color={opened.color} icon={opened.icon} collectionId={opened.id} className="h-9 w-11" />
                <h2 className="text-xl font-semibold tracking-tight">{opened.name}</h2>
                <span className="text-sm text-zinc-500">
                  {(saves?.total ?? opened.count).toLocaleString()} save{(saves?.total ?? opened.count) === 1 ? "" : "s"}
                  {(opened.total ?? opened.count) > opened.count && `, ${(opened.total ?? 0).toLocaleString()} with what's inside`}
                </span>
                <Button size="sm" variant="ghost" className="ml-auto" aria-expanded={details} onClick={() => setDetails(!details)}>
                  {details ? "Hide details" : "Details and AI tools"}
                </Button>
              </div>
            )}
            {opened && !details && opened.description && <p className="-mt-2 text-sm text-zinc-500 dark:text-zinc-400">{opened.description}</p>}
            {opened && details && (
              <CollectionHeader collection={opened} all={collections} count={saves?.total ?? opened.count} act={act} onDeleted={() => navigate(upHref)} />
            )}
            {view.type === "collection" && !opened && overview && <Notice tone="warning">That collection doesn't exist any more.</Notice>}

            {pickedFolders.length > 0 && (
              <div role="toolbar" aria-label="Picked collections" className="sticky top-2 z-10 flex flex-wrap items-center gap-2 rounded-2xl border border-indigo-200 bg-indigo-50/95 px-4 py-2.5 text-sm shadow dark:border-indigo-900 dark:bg-indigo-950/90">
                <span className="font-medium">
                  {pickedFolders.length} collection{pickedFolders.length === 1 ? "" : "s"} picked
                </span>
                <Button size="sm" onClick={() => void moveFolders()}>
                  Move to…
                </Button>
                <Button size="sm" variant="danger" onClick={() => void deleteFolders()}>
                  Delete…
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPickedFolders(shownFolders.map((c) => c.id))}>
                  Pick all
                </Button>
                <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setPickedFolders([])}>
                  Clear
                </Button>
              </div>
            )}

            <div key={`${viewKey}|${space?.id}`} className={`space-y-5 ${slide}`}>
              {/* Folders first, always. */}
              {shownFolders.length > 0 && (
                <ul className="grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-4" aria-label={opened ? `Collections in ${opened.name}` : "Your collections"}>
                  {shownFolders.map((collection, index) => (
                    <FolderTile
                      key={collection.id}
                      collection={collection}
                      index={index}
                      showPath={Boolean(wanted)}
                      picked={pickedFolders.includes(collection.id)}
                      picking={pickedFolders.length > 0}
                      dragIds={pickedFolders.includes(collection.id) ? pickedFolders : [collection.id]}
                      onPick={(event) => pickFolder(collection, event)}
                      onDrop={(event) => dropOn(event, { collection })}
                      onMenu={(event) =>
                        openMenu(
                          event,
                          collectionMenuItems(collection, {
                            all: collections,
                            spaces,
                            ask,
                            extra: [
                              {
                                label: pickedFolders.includes(collection.id) ? "Unpick" : "Pick",
                                icon: icons.select,
                                hint: "Ctrl+click",
                                onSelect: () => setPickedFolders((old) => pickFrom([], old, null, collection.id, false)),
                              },
                            ],
                          }),
                          collection.name,
                        )
                      }
                    />
                  ))}
                </ul>
              )}
              {wanted && shownFolders.length === 0 && <p className="text-sm text-zinc-500">No collection in {space?.name} matches “{find.trim()}”.</p>}

              {!wanted && !opened && folders.length === 0 && overview && (
                <p className="rounded-2xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
                  No collections in {space?.name ?? "this space"} yet. Press “New collection” to make the first one.
                </p>
              )}

              {/* Then the saves that sit right in this collection. */}
              {!wanted && opened && saves && saves.items.length > 0 && (
                <>
                  {folders.length > 0 && <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Saves in {opened.name}</h3>}
                  <ul className="grid grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-4" aria-label={`Saves in ${opened.name}`}>
                    {saves.items.map((item, index) => (
                      <li key={item.id} className="kw-pop flex" style={{ "--i": index + shownFolders.length } as CSSProperties}>
                        <LibraryCard
                          item={item}
                          selecting={pickedSaves.length > 0}
                          selected={pickedSaves.includes(item.id)}
                          onSelect={(event) => pickSave(item, event)}
                          dragIds={pickedSaves.includes(item.id) ? pickedSaves : undefined}
                          fromId={opened.id}
                          from={{ id: opened.id, name: opened.name }}
                          onChange={updateSave}
                          menuItems={
                            pickedSaves.length > 1 && pickedSaves.includes(item.id)
                              ? selectionMenuItems(pickedSaves, { onDone: refreshItems, onClear: () => setPickedSaves([]) })
                              : undefined
                          }
                        />
                      </li>
                    ))}
                  </ul>
                  {saves.items.length < saves.total && (
                    <div className="flex justify-center">
                      <Button variant="secondary" onClick={() => void loadMore()}>
                        Show more ({(saves.total - saves.items.length).toLocaleString()} left)
                      </Button>
                    </div>
                  )}
                </>
              )}
              {!wanted && opened && saves && saves.items.length === 0 && folders.length === 0 && (
                <p className="rounded-2xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
                  Nothing in here yet. Drag saves onto this collection, right-click a save and choose “Collections…”, or
                  let the AI sort.
                </p>
              )}
            </div>

            {pickedSaves.length > 0 && opened && (
              <BulkBar
                ids={pickedSaves}
                shownIn={opened.id}
                onDone={() => {
                  refreshItems();
                  refreshLists();
                }}
                onClear={() => setPickedSaves([])}
                onSelectAll={() => setPickedSaves((saves?.items ?? []).map((i) => i.id))}
                allSelected={pickedSaves.length === (saves?.items.length ?? 0)}
              />
            )}
            <p className="text-xs tabular-nums text-zinc-400" title={`A space holds up to ${limit} collections`}>
              {inSpace.length} of {limit} collections used in {space?.name ?? "this space"}
            </p>
          </section>
        )}

        {(view.type === "review" || view.type === "unsorted" || view.type === "all") && (
          <section className="space-y-4">
            <ViewHeader view={view} count={items.length} busy={busy} onSort={() => startSort(view.type === "review" ? "review" : "unsorted")} />
            {items.length === 0 ? (
              <EmptyView view={view} waiting={waiting} />
            ) : (
              <ul className="space-y-3">
                {items.map((item) => (
                  <li key={item.id}>
                    <ItemCard
                      item={item}
                      collections={collections}
                      fromId={null}
                      onMove={(toId) => act(() => sortingApi.move(item.id, null, toId))}
                      onRemove={(collectionId) => act(() => sortingApi.removeFrom(item.id, collectionId))}
                      onChange={(card) => setItems((old) => old.map((o) => (o.id === card.id ? card : o)))}
                      actions={
                        item.needs_review ? (
                          <ReviewActions item={item} room={roomHere} onAccept={(choice) => act(() => sortingApi.accept(item.id, choice))} />
                        ) : undefined
                      }
                    />
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
      {menu}
      {dialog}
    </div>
  );
}

/** One step of the path. Collections and saves can be dropped on it. */
function Crumb({ href, current, onDrop, children }: { href: string; current: boolean; onDrop: (event: DragEvent) => void; children: ReactNode }) {
  const [over, setOver] = useState(false);
  return (
    <a
      href={href}
      aria-current={current ? "page" : undefined}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(COLLECTION_DRAG) || e.dataTransfer.types.includes(ITEMS_DRAG)) {
          e.preventDefault();
          setOver(true);
        }
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false);
        onDrop(e);
      }}
      className={`max-w-48 truncate rounded-lg px-2 py-1 transition ${
        over
          ? "bg-indigo-600 text-white"
          : current
            ? "font-semibold text-zinc-900 dark:text-white"
            : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-white"
      }`}
    >
      {children}
    </a>
  );
}

const TAB = "-mb-px flex items-center gap-2 rounded-t-lg border-b-2 px-4 py-2 text-sm font-medium transition";
const TAB_ON = "border-indigo-600 text-zinc-900 dark:border-indigo-400 dark:text-white";
const TAB_OFF = "border-transparent text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white";

/** Needs review / Not in a collection: tabs like the spaces, at the end of
 * the row. Needs review gets an accent count when something is waiting. */
function ViewTab({ href, active, count, alert = false, children }: { href: string; active: boolean; count: number; alert?: boolean; children: ReactNode }) {
  return (
    <a href={href} role="tab" aria-selected={active} className={`${TAB} ${active ? TAB_ON : TAB_OFF}`}>
      {children}
      <span className={`rounded-full px-1.5 text-xs tabular-nums ${alert ? "bg-indigo-600 font-semibold text-white dark:bg-indigo-500 dark:text-zinc-950" : "text-zinc-400"}`}>
        {count.toLocaleString()}
      </span>
    </a>
  );
}

/** The spaces, as tabs. Right-click one to rename, colour, move or delete it. */
function SpaceTabs({
  spaces,
  current,
  limit,
  ask,
  act,
  hrefOf,
  onDrop,
  view,
  review,
  unsorted,
}: {
  view: "review" | "unsorted" | null;
  review: number;
  unsorted: number;
  spaces: Space[];
  current: number | undefined;
  limit: number;
  ask: Ask;
  act: (task: () => Promise<unknown>) => void;
  hrefOf: (id: number | undefined) => string;
  onDrop: (event: DragEvent, space: Space) => void;
}) {
  const [openMenu, menu] = useContextMenu();
  const [over, setOver] = useState<number | null>(null);

  async function add() {
    const name = await ask.text({ title: "New space", label: "Name, like Work or Trips", confirm: "Add", maxLength: 40 });
    if (!name) return;
    act(async () => {
      const made = await organizeApi.createSpace(name);
      toast(`Added the space “${name}”.`);
      if (made.created_space) navigate(`/collections?space=${made.created_space}`);
    });
  }

  function itemsFor(space: Space, index: number): MenuItem[] {
    return [
      {
        label: "Rename…",
        icon: icons.pencil,
        onSelect: async () => {
          const name = await ask.text({ title: "Rename space", label: "Name", value: space.name, maxLength: 40 });
          if (name && name !== space.name) act(() => organizeApi.changeSpace(space.id, { name }));
        },
      },
      { kind: "colors", label: "Colour", value: space.color, onPick: (color) => act(() => organizeApi.changeSpace(space.id, { color })) },
      { kind: "divider" },
      { label: "Move left", icon: icons.up, disabled: index === 0, onSelect: () => act(() => organizeApi.changeSpace(space.id, { index: index - 1 })) },
      { label: "Move right", icon: icons.down, disabled: index === spaces.length - 1, onSelect: () => act(() => organizeApi.changeSpace(space.id, { index: index + 1 })) },
      { kind: "divider" },
      {
        label: "Delete…",
        icon: icons.trash,
        danger: true,
        disabled: spaces.length < 2,
        onSelect: async () => {
          const other = spaces.find((s) => s.id !== space.id);
          const sure = await ask.confirm({
            title: `Delete the space “${space.name}”?`,
            body: space.collections
              ? `Its ${space.collections} collection${space.collections === 1 ? "" : "s"} move to “${other?.name}”. Nothing else is lost.`
              : "It's empty, so nothing else changes.",
            confirm: "Delete",
            danger: true,
          });
          if (!sure) return;
          act(async () => {
            const left = await organizeApi.deleteSpace(space.id);
            toast(`Deleted the space “${space.name}”.`);
            navigate(hrefOf(left.moved_to));
          });
        },
      },
    ];
  }

  return (
    <div role="tablist" aria-label="Spaces" className="flex flex-wrap items-center gap-1 border-b border-zinc-200 dark:border-zinc-800">
      {spaces.map((space, index) => {
        const active = space.id === current;
        return (
          <a
            key={space.id}
            role="tab"
            aria-selected={active}
            href={`#${hrefOf(space.id)}`}
            onContextMenu={(event) => openMenu(event, itemsFor(space, index), space.name)}
            onDragOver={(e) => {
              if (e.dataTransfer.types.includes(COLLECTION_DRAG)) {
                e.preventDefault();
                setOver(space.id);
              }
            }}
            onDragLeave={() => setOver(null)}
            onDrop={(e) => {
              setOver(null);
              onDrop(e, space);
            }}
            className={`${TAB} ${over === space.id ? "border-indigo-500 bg-indigo-600 text-white" : active ? TAB_ON : TAB_OFF}`}
          >
            {space.color && <span className={`h-2 w-2 rounded-full ${COLOR_DOTS[space.color] ?? "bg-zinc-400"}`} aria-hidden="true" />}
            {space.name}
            <span className="text-xs tabular-nums text-zinc-400">{space.collections}</span>
          </a>
        );
      })}
      <button
        type="button"
        onClick={() => void add()}
        disabled={spaces.length >= limit}
        title={spaces.length >= limit ? `Up to ${limit} spaces` : "Add a space"}
        aria-label="Add a space"
        className="mb-1 ml-1 flex h-7 w-7 items-center justify-center rounded-lg p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-30 dark:hover:bg-zinc-800 dark:hover:text-white"
      >
        {icons.plus}
      </button>
      <span className="ml-auto" />
      <ViewTab href="#/collections/review" active={view === "review"} count={review} alert={review > 0}>
        Needs review
      </ViewTab>
      <ViewTab href="#/collections/unsorted" active={view === "unsorted"} count={unsorted}>
        Not in a collection
      </ViewTab>
      {menu}
    </div>
  );
}

/** One collection, as a folder. Click opens it; the box (or Ctrl / Shift click) picks it. */
function FolderTile({
  collection,
  index,
  showPath,
  picked,
  picking,
  dragIds,
  onPick,
  onDrop,
  onMenu,
}: {
  collection: Collection;
  index: number;
  showPath: boolean;
  picked: boolean;
  picking: boolean;
  dragIds: number[];
  onPick: (event: MouseEvent) => void;
  onDrop: (event: DragEvent) => void;
  onMenu: (event: MouseEvent) => void;
}) {
  const [over, setOver] = useState(false);
  const inside = (collection.total ?? collection.count) - collection.count;
  return (
    <li className="kw-pop" style={{ "--i": index } as CSSProperties}>
      <a
        href={`#/collections/${collection.id}`}
        data-testid={`folder-${collection.id}`}
        data-open={over}
        data-picked={picked}
        draggable
        aria-label={collection.name}
        onDragStart={(e) => {
          e.dataTransfer.setData(COLLECTION_DRAG, JSON.stringify({ ids: dragIds }));
          e.dataTransfer.effectAllowed = "move";
        }}
        onDragOver={(e) => {
          const types = e.dataTransfer.types;
          if (types.includes(ITEMS_DRAG) || types.includes(COLLECTION_DRAG)) {
            e.preventDefault();
            setOver(true);
          }
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          setOver(false);
          onDrop(e);
        }}
        onClick={(e) => {
          if (e.ctrlKey || e.shiftKey || e.metaKey) {
            e.preventDefault();
            onPick(e);
          }
        }}
        onContextMenu={onMenu}
        className="kw-folder kw-tile group flex h-full flex-col gap-3 p-5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
      >
        <div className="flex items-start justify-between">
          <FolderIcon color={collection.color} icon={collection.icon} collectionId={collection.id} className="h-[4.5rem] w-[5.5rem]" />
          <button
            type="button"
            role="checkbox"
            aria-checked={picked}
            aria-label={`Pick ${collection.name}`}
            title="Pick (Ctrl+click also works; Shift+click picks a run)"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onPick(e);
            }}
            className={`flex h-5 w-5 items-center justify-center rounded-md border-2 p-0.5 transition ${
              picked
                ? "border-indigo-600 bg-indigo-600 text-white"
                : `border-zinc-300 text-transparent hover:border-indigo-400 dark:border-zinc-600 ${picking ? "opacity-100" : "opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"}`
            }`}
          >
            {icons.check}
          </button>
        </div>
        <div className="min-w-0">
          <h3 className="truncate text-[15px] font-semibold tracking-tight" title={collection.path}>
            {collection.name}
          </h3>
          <p className="mt-0.5 truncate text-xs text-zinc-500 dark:text-zinc-400">
            {showPath && collection.path !== collection.name
              ? collection.path.slice(0, collection.path.lastIndexOf(" / "))
              : `${collection.count.toLocaleString()} save${collection.count === 1 ? "" : "s"}${inside > 0 ? ` · ${inside.toLocaleString()} inside` : collection.has_children ? " · has collections" : ""}`}
          </p>
        </div>
        {!collection.ai_allowed && (
          <span className="absolute bottom-3 right-3 rounded-full bg-zinc-900/5 px-2 py-0.5 text-[10px] font-medium text-zinc-500 dark:bg-white/10 dark:text-zinc-400" title="The AI doesn't sort into this one">
            AI off
          </span>
        )}
      </a>
    </li>
  );
}

function ViewHeader({
  view,
  count,
  busy,
  onSort,
}: {
  view: { type: "review" | "unsorted" | "all" };
  count: number;
  busy: boolean;
  onSort: () => void;
}) {
  const titles = { review: "Needs review", unsorted: "Not in a collection", all: "All with notes" };
  return (
    <div className="flex flex-wrap items-center gap-3">
      <h2 className="text-lg font-semibold tracking-tight">{titles[view.type]}</h2>
      <span className="text-sm text-zinc-500">{count.toLocaleString()}</span>
      {view.type === "review" && (
        <span className="text-sm text-zinc-500 dark:text-zinc-400">The AI wasn't sure where these go. Pick for it.</span>
      )}
      {view.type !== "all" && count > 0 && (
        <Button size="sm" variant="secondary" className="ml-auto" disabled={busy} onClick={onSort}>
          <span className="h-4 w-4">{icons.sparkle}</span>
          AI sort these
        </Button>
      )}
    </div>
  );
}

function EmptyView({ view, waiting }: { view: Selection; waiting: number }) {
  const text =
    view.type === "review"
      ? "Nothing to review. The AI was sure about everything so far."
      : view.type === "unsorted"
        ? "Every save with notes is in a collection."
        : view.type === "all"
          ? waiting > 0
            ? "No notes yet. Start them under “Let the AI organise”."
            : "No notes yet. Get transcripts first, on the Transcripts screen."
          : "Nothing here yet. Drag a save onto this collection, use a save's Collection button in the Library, or let AI sort fill it.";
  return <p className="rounded-2xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">{text}</p>;
}
