// Library (#/library): every save as a grid of pictures, with a word search
// and filters for status, type, collection, tags (several at once), creator
// and progress, and many sort orders. The platform comes from the picker at
// the top left. The filters live in the address (#/library?tags=pasta), so
// Back returns to the same view. Hovering a card shows quick buttons (tags,
// collection, plan, unsave); "Select" does the same to many saves at once.
import { useCallback, useEffect, useState, type MouseEvent, type ReactNode } from "react";

import EmptyState from "../components/EmptyState";
import { icons } from "../components/icons";
import { Button, Notice, Segmented } from "../components/ui";
import LibraryCard from "../features/library/LibraryCard";
import { selectionMenuItems } from "../features/library/saveMenu";
import {
  DEFAULT_QUERY,
  SORT_LABELS,
  libraryApi,
  paramsToQuery,
  queryToParams,
  type LibraryFilters,
  type LibraryItem,
  type LibraryQuery,
  type SortOrder,
  type StatusFilter,
} from "../features/library/libraryApi";
import BulkBar from "../features/organize/BulkBar";
import { onOrganizeChange } from "../features/organize/organizeApi";
import { errorText } from "../lib/api";
import { navigate, useRoute } from "../lib/router";
import { Tip } from "../lib/tips";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "processed", label: "With notes" },
  { value: "waiting", label: "Needs notes" },
  { value: "failed", label: "Couldn't read" },
];

const GRID: Record<string, string> = {
  small: "grid-cols-[repeat(auto-fill,minmax(130px,1fr))] gap-3",
  medium: "grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-4",
  large: "grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-5",
};

const selectClass =
  "max-w-48 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm text-zinc-800 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
      <span className="sr-only">{label}</span>
      <select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} className={selectClass}>
        {children}
      </select>
    </label>
  );
}

function tagList(query: LibraryQuery): string[] {
  return [...new Set([query.tag, ...query.tags.split(",")].map((t) => t.trim()).filter(Boolean))];
}

function greeting(name: string): string | null {
  if (!name.trim()) return null;
  const hour = new Date().getHours();
  const part = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  return `Good ${part}, ${name.trim()}`;
}

export default function LibraryPage({
  cardSize = "medium",
  cardActions = true,
  name = "",
}: {
  cardSize?: "small" | "medium" | "large";
  cardActions?: boolean;
  name?: string; // the user's name, for the greeting
}) {
  const route = useRoute();
  const query = paramsToQuery(route.query);
  const queryKey = queryToParams(query).toString();
  const [filters, setFilters] = useState<LibraryFilters | null>(null);
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<number[]>([]);
  const [lastPicked, setLastPicked] = useState<number | null>(null);
  const [reloads, setReloads] = useState(0);
  const [words, setWords] = useState(query.q);
  // Back or a link changed the words: show them.
  useEffect(() => {
    setWords((now) => (now.trim() === query.q ? now : query.q));
  }, [query.q]);
  // Typing in the search box updates the address after a short pause.
  useEffect(() => {
    if (words === query.q) return;
    const timer = window.setTimeout(() => change({ q: words.trim() }), 300);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [words]);

  const reloadFilters = useCallback(() => {
    libraryApi.filters().then(setFilters).catch(() => undefined);
  }, []);
  useEffect(reloadFilters, [reloadFilters]);
  // Something was filed or tagged elsewhere (e.g. dropped on the sidebar): refresh.
  useEffect(
    () =>
      onOrganizeChange(() => {
        reloadFilters();
        setReloads((n) => n + 1);
      }),
    [reloadFilters],
  );

  useEffect(() => {
    let stale = false;
    setError(null);
    libraryApi
      .items(paramsToQuery(new URLSearchParams(queryKey)))
      .then((page) => {
        if (stale) return;
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((e) => !stale && setError(errorText(e)));
    return () => {
      stale = true;
    };
  }, [queryKey, reloads]);

  // A new filter starts a new selection.
  useEffect(() => {
    setSelected([]);
    setLastPicked(null);
  }, [queryKey]);

  // Esc stops selecting; Ctrl+A selects everything shown while selecting.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const tag = (event.target as HTMLElement | null)?.tagName ?? "";
      if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
      if (event.key === "Escape" && (selecting || selected.length)) {
        setSelecting(false);
        setSelected([]);
      } else if (selecting && event.ctrlKey && event.key.toLowerCase() === "a" && items) {
        event.preventDefault();
        setSelected(items.map((i) => i.id));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selecting, selected.length, items]);

  function change(update: Partial<LibraryQuery>) {
    const params = queryToParams({ ...query, ...update }).toString();
    navigate(`/library${params ? `?${params}` : ""}`);
  }

  async function loadMore() {
    if (!items) return;
    setLoadingMore(true);
    try {
      const page = await libraryApi.items(query, items.length);
      setItems([...items, ...page.items]);
      setTotal(page.total);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoadingMore(false);
    }
  }

  function pick(item: LibraryItem, event: MouseEvent) {
    if (!items) return;
    setSelecting(true);
    if (event.shiftKey && lastPicked !== null) {
      const from = items.findIndex((i) => i.id === lastPicked);
      const to = items.findIndex((i) => i.id === item.id);
      const run = items.slice(Math.min(from, to), Math.max(from, to) + 1).map((i) => i.id);
      setSelected((old) => [...new Set([...old, ...run])]);
    } else {
      setSelected((old) => (old.includes(item.id) ? old.filter((id) => id !== item.id) : [...old, item.id]));
    }
    setLastPicked(item.id);
  }

  const shownIn = /^\d+$/.test(query.collection_id) ? Number(query.collection_id) : null;
  const shownLabel = filters?.collections.find((c) => Number(c.id) === shownIn)?.label;
  const shownCollection = shownIn !== null && shownLabel ? { id: shownIn, name: String(shownLabel) } : null;
  const chosenTags = tagList(query);
  const setTags = (list: string[]) => change({ tag: "", tags: list.join(",") });
  const updateItem = (changed: LibraryItem) => setItems((old) => old?.map((i) => (i.id === changed.id ? changed : i)) ?? old);
  const filtered = queryKey !== "" && !(queryKey.startsWith("sort=") && !queryKey.includes("&"));
  const showBar = selecting || selected.length > 0;
  return (
    <div className="mx-auto max-w-7xl px-8 py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          {greeting(name) && <p className="text-sm font-medium text-indigo-600 dark:text-indigo-400">{greeting(name)}</p>}
          <h1 className="text-2xl font-semibold tracking-tight" data-tour="library">Library</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {items === null ? "Loading…" : `${total.toLocaleString()} save${total === 1 ? "" : "s"}${filtered ? " match" : ""}`}
            {query.creator && (
              <>
                {" "}
                from <b>@{query.creator}</b>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {filtered && (
            <Button variant="ghost" size="sm" onClick={() => { setWords(""); change({ ...DEFAULT_QUERY, sort: query.sort }); }}>
              Clear filters
            </Button>
          )}
          <Button
            variant={showBar ? "primary" : "secondary"}
            size="sm"
            onClick={() => {
              setSelecting(!showBar);
              setSelected([]);
            }}
            title="Pick several saves (or Ctrl-click / Shift-click a card)"
          >
            <span className="h-4 w-4">{icons.select}</span>
            {showBar ? "Stop selecting" : "Select"}
          </Button>
        </div>
      </header>

      <div className="mt-5 flex flex-wrap items-center gap-2">
        <label className="relative min-w-56 flex-1">
          <span className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400">{icons.search}</span>
          <input
            type="search"
            value={words}
            onChange={(event) => setWords(event.target.value)}
            placeholder="Find in titles, captions, transcripts, notes and tags"
            aria-label="Find in the library"
            className="w-full rounded-lg border border-zinc-300 bg-white py-1.5 pl-8 pr-2.5 text-sm text-zinc-800 placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
        </label>
        <Segmented label="Show" value={query.status} options={STATUS_OPTIONS} onChange={(status) => change({ status })} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Select label="Type" value={query.kind} onChange={(kind) => change({ kind })}>
            <option value="">All types</option>
            {filters?.kinds
              .filter((k) => k.count > 0 || k.id === query.kind)
              .map((k) => (
                <option key={k.id} value={k.id}>
                  {k.label} ({k.count})
                </option>
              ))}
          </Select>
          <Select label="Collection" value={query.collection_id} onChange={(collection_id) => change({ collection_id })}>
            <option value="">All collections</option>
            <option value="none">In no collection ({(filters?.no_collection ?? 0).toLocaleString()})</option>
            {filters?.collections.map((c) => (
              <option key={c.id} value={String(c.id)}>
                {" ".repeat((c.depth ?? 0) * 2)}
                {c.label} ({c.count})
              </option>
            ))}
          </Select>
          <Select label="Tag" value="" onChange={(tag) => tag && setTags([...chosenTags, tag])}>
            <option value="">{chosenTags.length ? "And tag…" : "Any tag"}</option>
            {filters?.tags
              ?.filter((t) => !chosenTags.includes(String(t.id)))
              .map((t) => (
                <option key={t.id} value={String(t.id)}>
                  #{t.label} ({t.count})
                </option>
              ))}
          </Select>
          <Select label="Creator" value={query.creator} onChange={(creator) => change({ creator })}>
            <option value="">Any creator</option>
            {query.creator && !(filters?.creators ?? []).some((c) => c.id === query.creator) && (
              <option value={query.creator}>@{query.creator}</option>
            )}
            {filters?.creators?.map((c) => (
              <option key={c.id} value={String(c.id)}>
                {c.label} ({c.count})
              </option>
            ))}
          </Select>
          <Select
            label="Progress"
            value={query.progress}
            onChange={(progress) => change({ progress: progress as LibraryQuery["progress"] })}
          >
            <option value="any">Any progress</option>
            <option value="not_started">Not started</option>
            <option value="started">In progress</option>
            <option value="done">Done</option>
          </Select>
          <Select label="Sort" value={query.sort} onChange={(sort) => change({ sort: sort as SortOrder })}>
            {(Object.keys(SORT_LABELS) as SortOrder[]).map((sort) => (
              <option key={sort} value={sort}>
                {SORT_LABELS[sort]}
              </option>
            ))}
          </Select>
        </div>
      </div>

      {chosenTags.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5" aria-label="Tag filters">
          <span className="text-xs text-zinc-500">With every tag:</span>
          {chosenTags.map((name) => (
            <span key={name} className="inline-flex items-center gap-1 rounded-full bg-indigo-50 py-0.5 pl-2.5 pr-1 text-xs font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300">
              #{name}
              <button
                type="button"
                aria-label={`Stop filtering by #${name}`}
                className="flex h-4 w-4 items-center justify-center rounded-full hover:bg-indigo-100 dark:hover:bg-indigo-900"
                onClick={() => setTags(chosenTags.filter((t) => t !== name))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="mt-6">
        {error && <Notice tone="error">{error}</Notice>}
        {items !== null && items.length === 0 && !error && (
          filtered ? (
            <EmptyState icon={icons.search} title="Nothing matches these filters" action={
              <Button variant="secondary" onClick={() => { setWords(""); change(DEFAULT_QUERY); }}>Clear filters</Button>
            }>
              Try another type, tag or collection, or clear the filters to see everything.
            </EmptyState>
          ) : (
            <EmptyState icon={icons.library} title="Your library is empty" action={
              <Button onClick={() => navigate("/import")}>Import your saves</Button>
            }>
              Import the data export from TikTok, YouTube, Instagram or Facebook and your saved videos show up here.
            </EmptyState>
          )
        )}
        {items === null && !error && (
          <div className={`grid ${GRID[cardSize]}`} aria-hidden="true">
            {Array.from({ length: 12 }, (_, i) => (
              <div key={i} className="aspect-[4/6] animate-pulse rounded-2xl bg-zinc-200/70 dark:bg-zinc-800/70" />
            ))}
          </div>
        )}
        {items && items.length > 0 && (
          <>
            {showBar ? (
              <p className="mb-3 text-xs text-zinc-500 dark:text-zinc-400">
                Click saves to pick them (Shift-click picks a run), then use the bar below.
              </p>
            ) : (
              cardActions && (
                <div className="mb-4">
                  <Tip id="library-quick-actions">
                    Point at a save to tag it, put it in a collection, add it to a plan or unsave it, without opening it.
                    Tick its box (or Ctrl-click, Shift-click) to pick several. Right-click for everything else, like
                    asking the AI about the ones you picked.
                  </Tip>
                </div>
              )
            )}
            <ul className={`grid ${GRID[cardSize]}`} aria-label="Saves">
              {items.map((item) => (
                <li key={item.id} className="flex">
                  <LibraryCard
                    item={item}
                    selecting={showBar}
                    selected={selected.includes(item.id)}
                    onSelect={(event) => pick(item, event)}
                    dragIds={selected.includes(item.id) ? selected : undefined}
                    fromId={null}
                    onChange={updateItem}
                    actions={cardActions}
                    from={shownCollection}
                    menuItems={
                      selected.length > 1 && selected.includes(item.id)
                        ? selectionMenuItems(selected, { onDone: () => setReloads((n) => n + 1), onClear: () => { setSelected([]); setSelecting(false); } })
                        : undefined
                    }
                    menuExtra={[
                      {
                        label: selected.includes(item.id) ? "Unselect" : "Select",
                        icon: icons.select,
                        hint: "Ctrl+click",
                        onSelect: () => {
                          setSelecting(true);
                          setSelected((old) => (old.includes(item.id) ? old.filter((id) => id !== item.id) : [...old, item.id]));
                          setLastPicked(item.id);
                        },
                      },
                      ...(item.author
                        ? [{ label: `More from @${item.author.replace(/^@/, "")}`, icon: icons.filter, onSelect: () => change({ creator: item.author!.replace(/^@/, "") }) }]
                        : []),
                      ...(item.kind && item.kind_label
                        ? [{ label: `More ${item.kind_label.toLowerCase()} saves`, icon: icons.filter, onSelect: () => change({ kind: item.kind! }) }]
                        : []),
                    ]}
                  />
                </li>
              ))}
            </ul>
            <div className="mt-8 flex flex-col items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
              <span>
                Showing {items.length.toLocaleString()} of {total.toLocaleString()}
              </span>
              {items.length < total && (
                <Button variant="secondary" disabled={loadingMore} onClick={() => void loadMore()}>
                  {loadingMore ? "Loading…" : "Show more"}
                </Button>
              )}
            </div>
          </>
        )}
        {showBar && items && (
          <BulkBar
            ids={selected}
            shownIn={shownIn}
            allSelected={items.length > 0 && selected.length === items.length}
            onSelectAll={() => setSelected(items.map((i) => i.id))}
            onClear={() => {
              setSelected([]);
              setSelecting(false);
            }}
            onDone={() => {
              reloadFilters();
              setReloads((n) => n + 1);
            }}
          />
        )}
      </div>
    </div>
  );
}
