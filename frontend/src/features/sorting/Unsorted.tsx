// Unsorted: saves with notes that aren't in any collection yet. Each one
// shows where the AI thinks it goes; one click accepts that, or pick another
// collection yourself. The AI's suggested tags wait here too. Shown on the
// Sort page and in Collections -> Unsorted.
import { SaveControls } from "../library/SaveControls";
import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";

import { useDialog } from "../../components/Dialog";
import JobCard from "../../components/JobCard";
import { Button, Notice } from "../../components/ui";
import { toast } from "../../components/Toasts";
import { icons } from "../../components/icons";
import { errorCode, errorText } from "../../lib/api";
import { isActive, onJobUpdate, useJobs, type Job } from "../../lib/jobs";
import { displayTitle } from "../library/libraryApi";
import Thumb from "../library/Thumb";
import BulkBar from "../organize/BulkBar";
import CollectionPicker from "../organize/CollectionPicker";
import FolderIcon from "../organize/FolderIcon";
import { announceChange, onOrganizeChange } from "../organize/organizeApi";
import { fitWord } from "./ItemCard";
import { sortingApi, type Collection, type ItemCard, type Space } from "./sortingApi";

export default function Unsorted({ limit, onCount }: { limit?: number; onCount?: (count: number) => void }) {
  const [items, setItems] = useState<ItemCard[] | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const [picked, setPicked] = useState<number[]>([]);
  const anchor = useRef<number | null>(null);
  const [resorting, setResorting] = useState(false);
  const [started, setStarted] = useState<Job | null>(null);
  const jobs = useJobs();
  const job = jobs.find((entry) => entry.id === started?.id) ?? started;
  const [ask, dialog] = useDialog();

  const load = useCallback(() => {
    sortingApi
      .library({ type: "unsorted" })
      .then((list) => {
        setItems(list);
        const remaining = new Set(list.map(item => item.id));
        setPicked(previous => previous.filter(id => remaining.has(id)));
        onCount?.(list.length);
      })
      .catch((e) => setError(errorText(e)));
    sortingApi
      .collections()
      .then((o) => {
        setCollections(o.collections);
        setSpaces(o.spaces ?? []);
      })
      .catch(() => undefined);
  }, [onCount]);
  useEffect(load, [load]);
  useEffect(() => onOrganizeChange(load), [load]);
  // New notes add saves here: refresh when a notes or sort job ends.
  useEffect(() => onJobUpdate((job) => (job.kind === "notes" || job.kind === "sort") && !isActive(job) && load()), [load]);

  async function act(task: () => Promise<unknown>) {
    setError(null);
    try {
      await task();
    } catch (e) {
      setError(errorText(e));
    }
    announceChange();
  }

  // The ones the AI has a suggestion for first: one click each.
  const list = [...(items ?? [])].sort(
    (a, b) => Number(!!suggestionOf(b, collections)) - Number(!!suggestionOf(a, collections)),
  );
  const withIdea = list.filter((item) => suggestionOf(item, collections)).length;
  const shown = limit && !all ? list.slice(0, limit) : list;

  const visibleIds = shown.map((item) => item.id);
  const selected = picked.filter((id) => visibleIds.includes(id));
  const showSelection = selecting || selected.length > 0;

  function clearSelection() {
    setSelecting(false);
    setPicked([]);
    anchor.current = null;
  }

  function pick(id: number, event: MouseEvent) {
    const start = anchor.current === null ? -1 : visibleIds.indexOf(anchor.current);
    anchor.current = id;
    const end = visibleIds.indexOf(id);
    if (event.shiftKey && start >= 0) {
      setPicked([...new Set([...selected, ...visibleIds.slice(Math.min(start, end), Math.max(start, end) + 1)])]);
    } else {
      setPicked(selected.includes(id) ? selected.filter((key) => key !== id) : [...selected, id]);
    }
  }

  async function resort() {
    if (!selected.length) return;
    const ids = selected;
    setResorting(true);
    setError(null);
    const start = (confirm = false) => sortingApi.resort("unsorted", true, confirm, ids);
    try {
      try {
        setStarted(await start());
      } catch (e) {
        if (errorCode(e) !== "confirm_cost") throw e;
        if (await ask.confirm({ title: "Use cloud AI to re-sort?", body: errorText(e), confirm: "Re-sort" })) {
          setStarted(await start(true));
        }
      }
    } catch (e) {
      setError(errorText(e));
    } finally {
      setResorting(false);
    }
  }

  async function acceptAll() {
    setBusy(true);
    try {
      const done = await sortingApi.acceptAll();
      toast(`Put ${done.accepted.toLocaleString()} save${done.accepted === 1 ? "" : "s"} where the AI suggested. Undo (top right) takes it back.`);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
      announceChange();
    }
  }

  return (
    <section className="space-y-3" aria-label="Unsorted" onKeyDown={(event) => {
      if (!showSelection || event.defaultPrevented ||
          (event.target as HTMLElement).closest("input, textarea, select, [contenteditable], [role=dialog]")) return;
      if (event.key === "Escape") {
        event.stopPropagation();
        clearSelection();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "a") {
        event.preventDefault();
        event.stopPropagation();
        setPicked(visibleIds);
      }
    }}>
      {dialog}
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          {items === null
            ? "…"
            : list.length === 0
              ? "Every save with notes is in a collection."
              : `${list.length.toLocaleString()} save${list.length === 1 ? " isn't" : "s aren't"} in a collection yet.`}
        </p>
        {shown.length > 0 && (
          <Button size="sm" variant="secondary" className="ml-auto" onClick={() => {
            if (showSelection) clearSelection();
            else setSelecting(true);
          }}>{showSelection ? "Stop selecting" : "Select"}</Button>
        )}
        {withIdea > 1 && !showSelection && (
          <Button size="sm" disabled={busy} onClick={() => void acceptAll()}>
            <span className="h-4 w-4">{icons.check}</span>
            Accept all {withIdea.toLocaleString()} suggestions
          </Button>
        )}
      </div>
      {error && (
        <Notice tone="error" onClose={() => setError(null)}>
          {error}
        </Notice>
      )}
      {shown.length > 0 && (
        <ul className="divide-y divide-zinc-100 overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
          {shown.map((item) => (
            <Row
              key={item.id}
              item={item}
              selecting={showSelection}
              selected={selected.includes(item.id)}
              onPick={(event) => pick(item.id, event)}
              collections={collections}
              spaces={spaces}
              onAccept={(collectionId) => act(() => sortingApi.accept(item.id, collectionId))}
              onTags={(names, accept) =>
                act(async () => {
                  const card = await sortingApi.answerTags(item.id, names, accept);
                  setItems((old) => old?.map((o) => (o.id === card.id ? card : o)) ?? old);
                })
              }
            />
          ))}
        </ul>
      )}
      {limit !== undefined && list.length > limit && (
        <Button variant="secondary" size="sm" onClick={() => { clearSelection(); setAll(!all); }}>
          {all ? "Show fewer" : `Show all ${list.length.toLocaleString()}`}
        </Button>
      )}
      {showSelection && shown.length > 0 && (
        <BulkBar ids={selected} shownIn={null} unsorted onDone={load} onClear={clearSelection}
          onSelectAll={() => setPicked(visibleIds)} allSelected={selected.length === visibleIds.length}
          extraActions={<Button size="sm" variant="secondary"
            disabled={resorting || selected.length === 0 || jobs.some((entry) => entry.kind === "sort" && isActive(entry)) || (!!job && isActive(job))}
            onClick={() => void resort()}>Re-sort selected</Button>} />
      )}
      {job && <JobCard job={job} name="AI suggestions" />}
    </section>
  );
}

/** The AI's best pick that's still one of the user's collections. */
export function suggestionOf(item: ItemCard, collections: Collection[]) {
  for (const pick of item.suggestions) {
    const collection = collections.find((c) => c.name.toLowerCase() === pick.name.toLowerCase());
    if (collection) return { collection, fit: fitWord(pick.confidence) };
  }
  return null;
}

function Row({
  item,
  selecting,
  selected,
  onPick,
  collections,
  spaces,
  onAccept,
  onTags,
}: {
  item: ItemCard;
  selecting: boolean;
  selected: boolean;
  onPick: (event: MouseEvent) => void;
  collections: Collection[];
  spaces: Space[];
  onAccept: (collectionId?: number) => void;
  onTags: (names: string[], accept: boolean) => void;
}) {
  const idea = suggestionOf(item, collections);
  return (
    <li className={`group flex gap-3 px-4 py-3 ${selected ? "bg-indigo-50 dark:bg-indigo-950/40" : ""}`}
      data-testid={`unsorted-${item.id}`} onClick={(event) => {
        if ((event.target as Element).closest("button, input, select, a")) return;
        if (selecting || event.shiftKey || event.ctrlKey || event.metaKey) {
          event.currentTarget.querySelector("button")?.focus();
          onPick(event);
        }
      }}>
      <button type="button" role="checkbox" aria-checked={selected} aria-label={`Select ${displayTitle(item)}`}
        title="Select (Ctrl+click also works, Shift+click selects a range)"
        className={`h-8 w-8 shrink-0 rounded-lg border p-1.5 focus-visible:opacity-100 ${
          selected ? "border-indigo-600 bg-indigo-600 text-white" : "border-zinc-300 dark:border-zinc-600"
        } ${selecting ? "" : "opacity-0 group-hover:opacity-100 [@media(hover:none)]:opacity-100"}`}
        onClick={onPick}>{selected && icons.check}</button>
      {!selecting && <SaveControls id={item.id} title={displayTitle(item)} select={false} />}
      <Thumb item={item} showDuration={false} className="h-16 w-12 shrink-0 rounded-lg" />
      <div className="min-w-0 flex-1 space-y-1.5">
        <a href={`#/item/${item.id}`} onClick={(event) => {
          if (selecting || event.shiftKey || event.ctrlKey || event.metaKey) {
            event.preventDefault();
            onPick(event);
          }
        }} className="block truncate text-sm font-medium hover:underline">
          {displayTitle(item)}
        </a>
        {item.summary && <p className="line-clamp-1 text-xs text-zinc-500 dark:text-zinc-400">{item.summary}</p>}
        <div className="flex flex-wrap items-center gap-2">
          {idea ? (
            <>
              <span className="inline-flex items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-300">
                <span className="text-zinc-400">AI suggests</span>
                <FolderIcon color={idea.collection.color} icon={idea.collection.icon} collectionId={idea.collection.id} className="h-4 w-5" />
                <b className="font-medium">{idea.collection.name}</b>
                <span className="text-zinc-400">({idea.fit})</span>
              </span>
              <Button size="sm" onClick={() => onAccept()}>
                Accept
              </Button>
            </>
          ) : (
            <span className="text-xs text-zinc-400">No suggestion yet.</span>
          )}
          <CollectionPicker
            collections={collections}
            spaces={spaces}
            label={`Choose a collection for “${displayTitle(item)}”`}
            suggested={item.suggestions.map((s) => s.name)}
            onPick={(collection) => onAccept(collection.id)}
          >
            {idea ? "Choose another" : "Choose a collection"}
          </CollectionPicker>
        </div>
        <TagIdeas item={item} onAnswer={onTags} />
      </div>
    </li>
  );
}

/** The AI's suggested tags for one save: click one to add it, × to say no. */
export function TagIdeas({ item, onAnswer }: { item: ItemCard; onAnswer: (names: string[], accept: boolean) => void }) {
  const ideas = item.tag_suggestions ?? [];
  if (ideas.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs" aria-label="Suggested tags">
      <span className="text-zinc-400">Suggested tags</span>
      {ideas.map((name) => (
        <span key={name} className="inline-flex items-center rounded-full border border-dashed border-zinc-300 dark:border-zinc-700">
          <button
            type="button"
            aria-label={`Add #${name}`}
            title={`Add #${name}`}
            onClick={() => onAnswer([name], true)}
            className="rounded-l-full py-0.5 pl-2 pr-1 text-zinc-600 hover:text-indigo-700 dark:text-zinc-300 dark:hover:text-indigo-300"
          >
            + #{name}
          </button>
          <button
            type="button"
            aria-label={`No to #${name}`}
            onClick={() => onAnswer([name], false)}
            className="rounded-r-full px-1.5 py-0.5 text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-100"
          >
            ×
          </button>
        </span>
      ))}
      {ideas.length > 1 && (
        <button type="button" onClick={() => onAnswer(ideas, true)} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
          Add all
        </button>
      )}
    </div>
  );
}
