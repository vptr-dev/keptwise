// The list of keyboard shortcuts, opened with "?" or the sidebar button.
import { useEffect, useRef } from "react";

export const PAGE_KEYS_NOTE = "Alt + 1 to 9";

const GROUPS: { title: string; keys: [string, string][] }[] = [
  {
    title: "Anywhere",
    keys: [
      ["Ctrl + K  or  /", "Open the command centre: search, go anywhere, do things"],
      ["#  /  @  >  ?", "In the command centre: tags, collections, creators, actions, ask the AI"],
      [PAGE_KEYS_NOTE, "Go to a page in the sidebar (in order)"],
      ["Ctrl + Shift + L", "Switch light / dark theme"],
      ["?", "Show these shortcuts"],
      ["Esc", "Close a panel or dialog"],
    ],
  },
  {
    title: "Saves, collections and tags",
    keys: [
      ["Right-click  or  Shift + F10", "Every action for it: tags, collections, plans, rename, colour, merge, delete…"],
      ["Ctrl + click", "Select several saves in the Library"],
      ["Shift + click", "Select a whole run of saves"],
      ["Ctrl + A", "Select every save shown (while selecting)"],
    ],
  },
  {
    title: "On a save's page",
    keys: [
      ["1 to 9", "Tick that step"],
      ["D", "Mark as done"],
      ["O", "Open the video on its platform"],
      ["Esc", "Go back"],
    ],
  },
];

export default function ShortcutsDialog({ onClose }: { onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="kw-fade fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/40 p-4" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        className="kw-rise kw-glass-pop w-full max-w-md rounded-2xl border bg-white p-6 shadow-xl dark:bg-zinc-900"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Keyboard shortcuts</h2>
          <button
            ref={closeRef}
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-lg px-2.5 py-1 text-lg leading-none text-zinc-500 hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:hover:bg-zinc-800"
          >
            ×
          </button>
        </div>
        {GROUPS.map((group) => (
          <section key={group.title} className="mt-5">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{group.title}</h3>
            <dl className="mt-2 space-y-1.5">
              {group.keys.map(([keys, what]) => (
                <div key={keys + what} className="flex items-center justify-between gap-4 text-sm">
                  <dt className="text-zinc-700 dark:text-zinc-300">{what}</dt>
                  <dd>
                    <kbd className="whitespace-nowrap rounded-md border border-zinc-300 bg-zinc-50 px-2 py-0.5 text-xs dark:border-zinc-700 dark:bg-zinc-800">
                      {keys}
                    </kbd>
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
    </div>
  );
}
