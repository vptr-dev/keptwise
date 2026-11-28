// "Unsave one by one": opens each save in the user's normal browser, where
// they press the save/bookmark button themselves; then one click ticks it off
// here and opens the next. Keptwise never logs in to or changes the platform.
import { SaveControls } from "./SaveControls";
import { useEffect, useRef, useState } from "react";

import ProgressBar from "../../components/ProgressBar";
import { icons } from "../../components/icons";
import { Button, Notice } from "../../components/ui";
import { UNSAVE_SHORTCUT_LABELS, type UnsaveShortcut } from "../../lib/theme";
import { errorText } from "../../lib/api";
import { displayTitle, libraryApi, type LibraryItem } from "./libraryApi";
import Thumb from "./Thumb";

let shortcutSequence = 0;
const HOTKEY_EVENT = "keptwise-unsave-hotkey";
type Bridge = { unsave_hotkey?: (value: UnsaveShortcut, generation: number) => Promise<boolean> };
const bridge = () => (window as Window & { pywebview?: { api?: Bridge } }).pywebview?.api;

export default function UnsaveWalkthrough({
  queue,
  shortcut = "off",
  onUnsaved,
  onClose,
}: {
  shortcut?: UnsaveShortcut;
  queue: LibraryItem[]; // the saves still to unsave, in order
  onUnsaved: (item: LibraryItem) => void;
  onClose: () => void;
}) {
  const [position, setPosition] = useState(0);
  const [done, setDone] = useState(0);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shortcutError, setShortcutError] = useState("");
  const item = queue[position];

  async function open(target: LibraryItem | undefined) {
    if (!target) return;
    setError(null);
    try {
      const result = await libraryApi.openInBrowser(target.id);
      if (!result.opened) setError("Couldn’t open the browser. Use Open again to retry.");
    } catch (e) {
      setError(errorText(e));
    }
  }

  async function markAndNext() {
    if (!item || inFlight.current) return;
    inFlight.current = true;
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
      inFlight.current = false;
      setBusy(false);
    }
  }

  const advance = useRef(markAndNext);
  advance.current = markAndNext;
  const hasItem = !!item;
  useEffect(() => {
    setShortcutError("");
    if (!hasItem || shortcut === "off") return;
    let active = true;
    let generation = 0;
    const register = () => {
      generation = ++shortcutSequence;
      const result = bridge()?.unsave_hotkey?.(shortcut, generation);
      if (!result) {
        setShortcutError("Global shortcuts are available in the Windows desktop app.");
        return;
      }
      void result.then(ok => {
        if (active) setShortcutError(ok ? "" : "Windows could not register this shortcut. Try another combination.");
      }).catch(() => {
        if (active) setShortcutError("Windows could not register this shortcut.");
      });
    };
    const trigger = (event: Event) => {
      if ((event as CustomEvent<number>).detail === generation) void advance.current();
    };
    window.addEventListener("pywebviewready", register);
    window.addEventListener("keptwise-frame", register);
    window.addEventListener(HOTKEY_EVENT, trigger);
    register();
    return () => {
      active = false;
      window.removeEventListener("pywebviewready", register);
      window.removeEventListener("keptwise-frame", register);
      window.removeEventListener(HOTKEY_EVENT, trigger);
      void bridge()?.unsave_hotkey?.("off", ++shortcutSequence).catch(() => undefined);
    };
  }, [hasItem, shortcut]);

  async function skip() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      setPosition((p) => p + 1);
      await open(queue[position + 1]);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
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
          <div className="group mt-4 flex items-center gap-3">
            <SaveControls id={item.id} title={displayTitle(item)} archived={item.deleted} />
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
            <Button variant="ghost" disabled={busy} onClick={() => void skip()}>
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
      {hasItem && shortcut !== "off" && (
        <p className="mt-3 text-xs text-zinc-500" role="status">
          {shortcutError || `${UNSAVE_SHORTCUT_LABELS[shortcut]} marks this video done even from your browser.`}
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
