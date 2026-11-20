// Unsave (#/unsave): saves whose notes are kept here, so the user
// can remove them from the platform themselves. The app never touches the
// user's TikTok, YouTube, Instagram or Facebook account.
import { useEffect, useState } from "react";

import EmptyState from "../components/EmptyState";
import ProgressBar from "../components/ProgressBar";
import { icons } from "../components/icons";
import { Button, Notice } from "../components/ui";
import {
  displayTitle,
  formatDate,
  libraryApi,
  type LibraryItem,
  type UnsaveList,
} from "../features/library/libraryApi";
import Thumb from "../features/library/Thumb";
import UnsaveWalkthrough from "../features/library/UnsaveWalkthrough";
import { errorText } from "../lib/api";
import { navigate } from "../lib/router";
import { Tip } from "../lib/tips";

function Row({ item, busy, onToggle }: { item: LibraryItem; busy: boolean; onToggle: (unsaved: boolean) => void }) {
  return (
    <li
      className={`flex items-center gap-3 px-4 py-2.5 transition ${
        item.unsaved ? "opacity-60" : ""
      }`}
    >
      <input
        type="checkbox"
        aria-label={`I've unsaved “${displayTitle(item)}”`}
        checked={item.unsaved}
        disabled={busy}
        onChange={(event) => onToggle(event.target.checked)}
        className="h-4 w-4 shrink-0 cursor-pointer accent-indigo-600"
      />
      <Thumb item={item} showDuration={false} className="h-12 w-10 shrink-0 rounded-lg" />
      <a href={`#/item/${item.id}`} className="min-w-0 flex-1 hover:underline">
        <span className={`block truncate text-sm font-medium ${item.unsaved ? "line-through" : ""}`}>{displayTitle(item)}</span>
        <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">
          {[item.kind_label, item.saved_at ? `saved ${formatDate(item.saved_at)}` : null].filter(Boolean).join(" · ")}
        </span>
      </a>
      <a
        href={item.url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-50 dark:text-indigo-400 dark:hover:bg-indigo-950/60"
      >
        <span className="h-3.5 w-3.5">{icons.external}</span> Open on {item.platform_name}
      </a>
    </li>
  );
}

export default function UnsavePage() {
  const [list, setList] = useState<UnsaveList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [hideDone, setHideDone] = useState(false);
  const [exported, setExported] = useState<{ path: string; count: number } | null>(null);
  const [exporting, setExporting] = useState(false);
  const [walkQueue, setWalkQueue] = useState<LibraryItem[] | null>(null);

  useEffect(() => {
    libraryApi.unsave().then(setList).catch((e) => setError(errorText(e)));
  }, []);

  async function toggle(item: LibraryItem, unsaved: boolean) {
    if (!list) return;
    setBusyId(item.id);
    try {
      const next = await libraryApi.patch(item.id, { unsaved });
      setList({
        ...list,
        items: list.items.map((old) => (old.id === next.id ? next : old)),
        left: list.left + (unsaved ? -1 : 1),
      });
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyId(null);
    }
  }

  /** Put a changed save back into the list (after it was ticked off). */
  function replaceItem(next: LibraryItem) {
    setList((old) =>
      old
        ? {
            ...old,
            items: old.items.map((item) => (item.id === next.id ? next : item)),
            left: old.left - (next.unsaved ? 1 : 0),
          }
        : old,
    );
  }

  function startWalkthrough() {
    const queue = (list?.items ?? []).filter((item) => !item.unsaved);
    if (queue.length === 0) return;
    setWalkQueue(queue);
    libraryApi.openInBrowser(queue[0].id).catch((e) => setError(errorText(e)));
  }

  async function exportCsv() {
    setExporting(true);
    setError(null);
    try {
      setExported(await libraryApi.exportCsv());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setExporting(false);
    }
  }

  const items = list?.items ?? [];
  const shown = hideDone ? items.filter((item) => !item.unsaved) : items;
  const platforms = [...new Set(shown.map((item) => item.platform_name))];
  const unsavedCount = items.length - (list?.left ?? 0);

  return (
    <div className="mx-auto max-w-3xl px-8 py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Unsave</h1>
          <p className="kw-tip text-sm text-zinc-500 dark:text-zinc-400">
            Mark a save after you unsave it yourself on TikTok or another platform. Archived saves can appear here as reminders.
          </p>
        </div>
        {items.length > 0 && (
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" disabled={exporting} onClick={() => void exportCsv()}>
              <span className="h-4 w-4">{icons.download}</span>
              {exporting ? "Exporting…" : "Export CSV"}
            </Button>
            <Button disabled={!list?.left || walkQueue !== null} onClick={startWalkthrough}>
              <span className="h-4 w-4">{icons.external}</span>
              Unsave one by one
            </Button>
          </div>
        )}
      </header>

      <div className="mt-5 space-y-4">
        <Tip id="unsave-how">
          Keptwise never logs in to or changes anything on TikTok, YouTube, Instagram or Facebook. “Unsave one by
          one” opens each video in your browser so you can unsave it yourself, then ticks it off here.
        </Tip>
        {list && (
          <p className="kw-tip text-sm text-zinc-600 dark:text-zinc-400">
            A save goes on this list by itself as soon as its notes are written, or when you delete it here.
          </p>
        )}
        {exported && (
          <Notice tone="success">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                Saved {exported.count.toLocaleString()} row{exported.count === 1 ? "" : "s"} to <strong className="break-all">{exported.path}</strong>
              </span>
              <Button size="sm" variant="secondary" onClick={() => void libraryApi.openDownloads().catch(() => undefined)}>
                Open folder
              </Button>
            </div>
          </Notice>
        )}
        {walkQueue && (
          <UnsaveWalkthrough queue={walkQueue} onUnsaved={replaceItem} onClose={() => setWalkQueue(null)} />
        )}
        {error && <Notice tone="error">{error}</Notice>}
        {!list && !error && <Notice>Loading…</Notice>}

        {list && items.length === 0 && (
          <EmptyState
            icon={icons.unsave}
            title="Nothing to unsave yet"
            action={<Button onClick={() => navigate("/transcripts")}>Write AI notes</Button>}
          >
            A save shows up here as soon as its notes are written. Then it's safe to remove it from the platform,
            because everything useful about it stays in Keptwise.
          </EmptyState>
        )}

        {items.length > 0 && (
          <>
            <div className="flex items-center gap-3">
              <ProgressBar done={unsavedCount} total={items.length} label="Unsaved so far" />
              <span className="shrink-0 text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
                {unsavedCount} of {items.length} unsaved
              </span>
              <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
                <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} className="accent-indigo-600" />
                Hide ones I've unsaved
              </label>
            </div>
            {shown.length === 0 && (
              <EmptyState icon={icons.check} title="All done">
                You've unsaved everything on this list.
              </EmptyState>
            )}
            {platforms.map((platform) => (
              <section key={platform} className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
                <h2 className="border-b border-zinc-200 px-4 py-2.5 text-sm font-semibold dark:border-zinc-800">{platform}</h2>
                <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
                  {shown
                    .filter((item) => item.platform_name === platform)
                    .map((item) => (
                      <Row key={item.id} item={item} busy={busyId === item.id} onToggle={(unsaved) => void toggle(item, unsaved)} />
                    ))}
                </ul>
              </section>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
