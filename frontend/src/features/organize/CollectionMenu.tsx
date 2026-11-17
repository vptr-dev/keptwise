// The "⋯" menu of a collection in the sidebar: new collection inside it,
// rename, colour, whether the AI may use it, delete.
import { useEffect, useRef, useState } from "react";

import type { Collection } from "../sorting/sortingApi";
import { COLOR_DOTS, COLORS } from "./organizeApi";

const ITEM =
  "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm text-zinc-700 hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-800";

export default function CollectionMenu({
  collection,
  onClose,
  onNewInside,
  onRename,
  onColor,
  onToggleAi,
  onDelete,
}: {
  collection: Collection;
  onClose: () => void;
  onNewInside: () => void;
  onRename: () => void;
  onColor: (color: string | null) => void;
  onToggleAi: () => void;
  onDelete: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [confirming, setConfirming] = useState(false);

  // Close on a click elsewhere or Esc.
  useEffect(() => {
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) onClose();
    };
    const esc = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [onClose]);

  return (
    <div
      ref={box}
      role="menu"
      aria-label={`${collection.name} options`}
      className="absolute right-1 top-full z-30 mt-1 w-56 rounded-xl border border-zinc-200 bg-white p-1.5 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
    >
      {confirming ? (
        <div className="p-2 text-sm">
          <p className="text-zinc-700 dark:text-zinc-200">
            Delete “{collection.name}”? Its videos stay in the app{collection.has_children ? ", and what's inside it moves up a level" : ""}.
          </p>
          <div className="mt-2 flex gap-2">
            <button type="button" className="rounded-md bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-500" onClick={onDelete}>
              Delete
            </button>
            <button type="button" className="rounded-md px-2.5 py-1 text-xs text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800" onClick={() => setConfirming(false)}>
              Keep it
            </button>
          </div>
        </div>
      ) : (
        <>
          <button type="button" role="menuitem" className={ITEM} onClick={onNewInside}>
            New collection inside
          </button>
          <button type="button" role="menuitem" className={ITEM} onClick={onRename}>
            Rename
          </button>
          <button
            type="button"
            role="menuitemcheckbox"
            aria-checked={collection.ai_allowed}
            className={ITEM}
            onClick={onToggleAi}
            title="When off, only you and your rules put videos here"
          >
            <span className="flex-1">The AI can file videos here</span>
            <span className={`h-4 w-7 rounded-full p-0.5 transition ${collection.ai_allowed ? "bg-indigo-600" : "bg-zinc-300 dark:bg-zinc-700"}`}>
              <span className={`block h-3 w-3 rounded-full bg-white transition ${collection.ai_allowed ? "translate-x-3" : ""}`} />
            </span>
          </button>
          <div className="px-2.5 pb-1 pt-2 text-xs text-zinc-500">Colour</div>
          <div className="flex flex-wrap gap-1.5 px-2.5 pb-2">
            {COLORS.map((color) => (
              <button
                key={color}
                type="button"
                aria-label={`Colour ${color}`}
                aria-pressed={collection.color === color}
                onClick={() => onColor(color)}
                className={`h-5 w-5 rounded-full ${COLOR_DOTS[color]} ${collection.color === color ? "ring-2 ring-zinc-900 ring-offset-1 dark:ring-white dark:ring-offset-zinc-900" : ""}`}
              />
            ))}
            <button
              type="button"
              aria-label="No colour"
              onClick={() => onColor(null)}
              className="h-5 w-5 rounded-full border border-dashed border-zinc-400 text-[10px] leading-4 text-zinc-500"
            >
              ×
            </button>
          </div>
          <div className="my-1 border-t border-zinc-100 dark:border-zinc-800" />
          <button type="button" role="menuitem" className={`${ITEM} text-red-600 dark:text-red-400`} onClick={() => setConfirming(true)}>
            Delete…
          </button>
        </>
      )}
    </div>
  );
}
