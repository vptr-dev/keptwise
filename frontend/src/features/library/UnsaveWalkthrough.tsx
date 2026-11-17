// "Unsave one by one": opens each save in the user's normal browser, where
// they press the save/bookmark button themselves; then one click ticks it off
// here and opens the next. Keptwise never logs in to or changes the platform.
import { useState } from "react";

import ProgressBar from "../../components/ProgressBar";
import { icons } from "../../components/icons";
import { Button, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { displayTitle, libraryApi, type LibraryItem } from "./libraryApi";
import Thumb from "./Thumb";

export default function UnsaveWalkthrough({
  queue,
  onUnsaved,
  onClose,
}: {
  queue: LibraryItem[]; // the saves still to unsave, in order
  onUnsaved: (item: LibraryItem) => void;
  onClose: () => void;
}) {
  const [position, setPosition] = useState(0);
  const [done, setDone] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const item = queue[position];

  async function open(target: LibraryItem | undefined) {
    if (!target) return;
    setError(null);
    try {
      await libraryApi.openInBrowser(target.id);
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function markAndNext() {
    if (!item) return;
    setBusy(true);
    setError(null);
    try {
      onUnsaved(await libraryApi.patch(item.id, { unsaved: true }));
      setDone((n) => n + 1);
      const next = queue[position + 1];
      setPosition((p) => p + 1);
      await open(next);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  function skip() {
    const next = queue[position + 1];
    setPosition((p) => p + 1);
    void open(next);
  }

  return (
    <section
      aria-label="Unsave one by one"
      className="rounded-2xl border border-indigo-200 bg-indigo-50/60 p-4 shadow-sm dark:border-indigo-900 dark:bg-indigo-950/30"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold">Unsave one by one</h2>
        <Button size="sm" variant="ghost" onClick={onClose}>
          Stop
        </Button>
      </div>
      <div className="mt-2 flex items-center gap-3">
        <ProgressBar done={position} total={queue.length} label="Gone through" />
        <span className="shrink-0 text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
          {Math.min(position + 1, queue.length)} of {queue.length}
        </span>
      </div>

      {item ? (
        <>
          <div className="mt-4 flex items-center gap-3">
            <Thumb item={item} showDuration={false} className="h-16 w-12 shrink-0 rounded-lg" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{displayTitle(item)}</p>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                It's open in your browser. Press the save button on {item.platform_name} so it's no longer saved, then
                come back here.
              </p>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button disabled={busy} onClick={() => void markAndNext()}>
              <span className="h-4 w-4">{icons.check}</span>
              {queue[position + 1] ? "Done, open the next one" : "Done"}
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => void open(item)}>
              <span className="h-4 w-4">{icons.external}</span>
              Open again
            </Button>
            <Button variant="ghost" disabled={busy} onClick={skip}>
              Skip
            </Button>
          </div>
        </>
      ) : (
        <p className="mt-4 text-sm">
          All done. You unsaved {done} {done === 1 ? "video" : "videos"}.{" "}
          <button type="button" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400" onClick={onClose}>
            Close
          </button>
        </p>
      )}
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </section>
  );
}
