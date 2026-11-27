import { useCallback, useEffect, useRef, useState, type CSSProperties, type MouseEvent } from "react";

import type { MenuItem } from "../components/ContextMenu";
import { useDialog } from "../components/Dialog";
import EmptyState from "../components/EmptyState";
import { toast } from "../components/Toasts";
import { icons } from "../components/icons";
import { Button, Notice } from "../components/ui";
import LibraryCard from "../features/library/LibraryCard";
import { DEFAULT_QUERY, displayTitle, libraryApi, type LibraryItem } from "../features/library/libraryApi";
import { announceChange, onOrganizeChange, organizeApi, type BulkAction } from "../features/organize/organizeApi";
import { api, errorText } from "../lib/api";
import { navigate } from "../lib/router";
import { Tip } from "../lib/tips";

type Tab = "deleted" | "gone";

const GRID: Record<string, string> = {
  small: "grid-cols-[repeat(auto-fill,minmax(130px,1fr))] gap-3",
  medium: "grid-cols-[repeat(auto-fill,minmax(170px,1fr))] gap-4",
  large: "grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-5",
};

export default function ArchivePage({ tab: wanted = null, cardSize = "medium" }: { tab?: string | null; cardSize?: "small" | "medium" | "large" }) {
  const tab: Tab = wanted === "gone" ? wanted : "deleted";
  const [page, setPage] = useState<{ total: number; items: LibraryItem[] } | null>(null);
  const [counts, setCounts] = useState<{ deleted: number; unsaved: number; gone: number } | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const last = useRef<number | null>(null);
  const [ask, dialog] = useDialog();

  const load = useCallback(() => {
    libraryApi
      .items(DEFAULT_QUERY, 0, true, tab)
      .then((p) => setPage({ total: p.total, items: p.items }))
      .catch((e) => setError(errorText(e)));
    libraryApi.archiveCounts().then(setCounts).catch(() => undefined);
  }, [tab]);
  useEffect(() => {
    setPage(null);
    setPicked([]);
    load();
  }, [load]);
  useEffect(() => onOrganizeChange(load), [load]);

  const items = page?.items ?? [];

  function pick(item: LibraryItem, event: MouseEvent) {
    const order = items.map((i) => i.id);
    const from = last.current;
    last.current = item.id;
    setPicked((old) => {
      if (event.shiftKey && from !== null && order.includes(from)) {
        const [a, b] = [order.indexOf(from), order.indexOf(item.id)].sort((x, y) => x - y);
        return [...new Set([...old, ...order.slice(a, b + 1)])];
      }
      return old.includes(item.id) ? old.filter((p) => p !== item.id) : [...old, item.id];
    });
  }

  async function bulk(ids: number[], action: BulkAction, done: string, undo?: BulkAction) {
    setError(null);
    try {
      await organizeApi.bulk({ item_ids: ids, action });
      setPicked([]);
      announceChange();
      toast(done, undo ? { undo: () => organizeApi.bulk({ item_ids: ids, action: undo }).then(announceChange) } : {});
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function purge(ids: number[]) {
    const one = ids.length === 1 ? items.find((i) => i.id === ids[0]) : undefined;
    const sure = await ask.confirm({
      title: one ? `Delete “${displayTitle(one)}” for good?` : `Delete ${ids.length} saves for good?`,
      body: "The notes, transcript, tags and picture go too. This can't be undone, and importing your export again won't bring them back.",
      confirm: "Delete for good",
      danger: true,
    });
    if (sure) void bulk(ids, "purge", `Deleted ${ids.length} save${ids.length === 1 ? "" : "s"} for good.`);
  }

  const [working, setWorking] = useState(false);
  async function batch(action: "restore" | "purge" | "archive_unavailable") {
    setWorking(true);
    setError(null);
    try {
      const path = "/api/archive/batch/" + action;
      const { count, token } = await api.get<{count: number; token: string}>(path);
      const verb = action === "purge" ? "Delete permanently" : action === "restore" ? "Restore" : "Archive";
      if (count && await ask.confirm({ title: verb + " " + count.toLocaleString() + " saves?",
        body: action === "purge" ? "This removes their notes, transcripts and pictures. Future imports will skip them. This is permanent."
          : "This includes every matching save for the selected platform, across all pages. You can undo this change.",
        confirm: verb, danger: action === "purge" })) {
        await api.post(path, { token }); setPicked([]); announceChange(); toast("Updated " + count.toLocaleString() + " saves.");
      }
    } catch (e) { setError(errorText(e)); } finally { setWorking(false); load(); }
  }

  async function loadMore() {
    if (!page) return;
    try {
      const more = await libraryApi.items(DEFAULT_QUERY, page.items.length, true, tab);
      setPage({ total: more.total, items: [...page.items, ...more.items] });
    } catch (e) {
      setError(errorText(e));
    }
  }

  const many = (ids: number[]) => `${ids.length} save${ids.length === 1 ? "" : "s"}`;
  function menuFor(item: LibraryItem): MenuItem[] {
    const ids = picked.length > 1 && picked.includes(item.id) ? picked : [item.id];
    const open: MenuItem[] = ids.length === 1 ? [{ label: "Open", icon: icons.open, onSelect: () => navigate(`/item/${item.id}`) }, { kind: "divider" }] : [];
    if (tab === "deleted") {
      return [
        ...open,
        { label: ids.length === 1 ? "Put back in the Library" : `Put ${many(ids)} back`, icon: icons.back, onSelect: () => void bulk(ids, "restore", `Put ${many(ids)} back in the Library.`, "delete") },
        { kind: "divider" },
        { label: ids.length === 1 ? "Delete for good…" : `Delete ${many(ids)} for good…`, icon: icons.trash, danger: true, onSelect: () => void purge(ids) },
      ];
    }
    return [
      ...open,
      { label: ids.length === 1 ? "Archive in Keptwise" : `Archive ${many(ids)}`, icon: icons.archive,
        onSelect: () => void bulk(ids, "delete", `Archived ${many(ids)}.`, "restore") },
    ];
  }

  const tabs: { id: Tab; label: string; count: number | undefined; href: string }[] = [
    { id: "deleted", label: "Archived", count: counts?.deleted, href: "#/archive" },
    { id: "gone", label: "Unavailable", count: counts?.gone, href: "#/archive/gone" },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-5 px-8 py-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight" data-tour="archive">Archive</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Archiving keeps your notes and collections. You can restore a save at any time before emptying the Archive.
        </p>
      </header>

      <div role="tablist" aria-label="Archive" className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800">
        {tabs.map((t) => (
          <a
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            href={t.href}
            className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition ${
              tab === t.id
                ? "border-indigo-600 text-zinc-900 dark:border-indigo-400 dark:text-white"
                : "border-transparent text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            }`}
          >
            {t.label}
            {t.count !== undefined && <span className="text-xs tabular-nums text-zinc-400">{t.count.toLocaleString()}</span>}
          </a>
        ))}
      </div>

      {tab === "deleted" ? (
        <Tip id="archive-deleted">
          Saves you archived in Keptwise wait here. <b>Put back</b> returns one to the Library exactly as it was. <b>Delete for good</b> removes
          it completely, and it won't come back when you import again.
        </Tip>
      ) : (
        <Tip id="archive-gone">
          Keptwise marked these videos as unavailable. If they still play for you,{" "}
          <a className="font-medium underline" href="#/sort">recheck them in Sort</a>. Your saved notes and collections are kept.
        </Tip>
      )}
      {error && <Notice tone="error" onClose={() => setError(null)}>{error}</Notice>}

      {page && page.total > 0 && <div className="flex flex-wrap gap-2">
        {tab === "deleted" ? <>
          <Button size="sm" variant="secondary" disabled={working} onClick={() => batch("restore")}>Restore all</Button>
          <Button size="sm" variant="danger" disabled={working} onClick={() => batch("purge")}>Empty archive…</Button>
        </> : <Button size="sm" variant="secondary" disabled={working} onClick={() => batch("archive_unavailable")}>Archive all unavailable…</Button>}
      </div>}
      {picked.length > 0 && (
        <div role="toolbar" aria-label="Picked saves" className="sticky top-2 z-10 flex flex-wrap items-center gap-2 rounded-2xl border border-indigo-200 bg-indigo-50/95 px-4 py-2.5 text-sm shadow dark:border-indigo-900 dark:bg-indigo-950/90">
          <span className="font-medium">{picked.length} picked</span>
          {tab === "deleted" ? (
            <>
              <Button size="sm" onClick={() => void bulk(picked, "restore", `Put ${many(picked)} back in the Library.`, "delete")}>
                Put back
              </Button>
              <Button size="sm" variant="danger" onClick={() => void purge(picked)}>
                Delete for good…
              </Button>
            </>
          ) : (
            <Button size="sm" variant="danger" onClick={() => void bulk(picked, "delete", `Archived ${many(picked)}.`, "restore")}>
              Archive
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setPicked(items.map((i) => i.id))}>
            Pick all shown
          </Button>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setPicked([])}>
            Clear
          </Button>
        </div>
      )}

      {page && items.length === 0 && (
        <EmptyState
          icon={icons.archive}
          title={tab === "deleted" ? "Nothing archived" : "No unavailable videos"}
        >
          {tab === "deleted"
            ? "Choose Archive on a save to move it here. You can put it back later."
            : "Videos that can no longer be opened on their platform appear here."}
        </EmptyState>
      )}
      {items.length > 0 && (
        <>
          <ul className={`grid ${GRID[cardSize]}`} aria-label={tab === "deleted" ? "Archived saves" : "Unavailable saves"}>
            {items.map((item, index) => (
              <li key={item.id} className="kw-pop flex" style={{ "--i": index } as CSSProperties}>
                <LibraryCard
                  item={item}
                  selecting={picked.length > 0}
                  selected={picked.includes(item.id)}
                  onSelect={(event) => pick(item, event)}
                  actions={false}
                  menuItems={menuFor(item)}
                />
              </li>
            ))}
          </ul>
          {items.length < (page?.total ?? 0) && (
            <div className="flex justify-center">
              <Button variant="secondary" onClick={() => void loadMore()}>
                Show more ({((page?.total ?? 0) - items.length).toLocaleString()} left)
              </Button>
            </div>
          )}
        </>
      )}
      {dialog}
    </div>
  );
}
