// The drop-down list at the top left: which platform's saves to manage.
// "All platforms" is the default; then each platform that has saves.
import { useEffect, useRef, useState } from "react";

import { PLATFORM_DOTS, type Scope } from "../lib/scope";
import { icons } from "./icons";

export default function PlatformPicker({
  scope,
  onChoose,
  compact = false,
}: {
  scope: Scope;
  onChoose: (platform: string | null) => void;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const current = scope.platforms.find((p) => p.id === scope.platform);
  const label = current ? current.label : "All platforms";

  useEffect(() => {
    if (!open) return;
    const away = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const esc = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  function pick(platform: string | null) {
    setOpen(false);
    if (platform !== scope.platform) onChoose(platform);
  }

  const dot = (id: string | null) =>
    id ? (
      <span className={`h-3 w-3 shrink-0 rounded-full ${PLATFORM_DOTS[id] ?? "bg-zinc-400"}`} aria-hidden="true" />
    ) : (
      <span className="h-3.5 w-3.5 shrink-0 text-zinc-500" aria-hidden="true">
        {icons.grid}
      </span>
    );

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Platform: ${label}. Change`}
        title={compact ? label : "Which platform's saves to show"}
        className={`flex w-full items-center gap-2 rounded-lg border border-zinc-200 bg-zinc-50 text-left text-sm font-medium text-zinc-800 transition hover:border-zinc-300 hover:bg-white focus-visible:outline-2 focus-visible:outline-indigo-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-100 dark:hover:border-zinc-700 dark:hover:bg-zinc-900 ${
          compact ? "justify-center px-2 py-2" : "px-2.5 py-1.5"
        }`}
      >
        {dot(scope.platform)}
        {!compact && (
          <>
            <span className="flex-1 truncate">{label}</span>
            <span className="h-3.5 w-3.5 text-zinc-400">{icons.down}</span>
          </>
        )}
      </button>
      {open && (
        <ul
          role="listbox"
          aria-label="Platform"
          className="absolute left-0 top-full z-40 mt-1 w-56 rounded-xl border border-zinc-200 bg-white p-1.5 shadow-lg dark:border-zinc-700 dark:bg-zinc-900"
        >
          {[{ id: null as string | null, label: "All platforms", count: scope.total }, ...scope.platforms].map((choice) => {
            const selected = choice.id === scope.platform;
            return (
              <li key={choice.id ?? "all"} role="option" aria-selected={selected}>
                <button
                  type="button"
                  onClick={() => pick(choice.id)}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm ${
                    selected
                      ? "bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300"
                      : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-200 dark:hover:bg-zinc-800"
                  }`}
                >
                  {dot(choice.id)}
                  <span className="flex-1">{choice.label}</span>
                  <span className="text-xs tabular-nums text-zinc-400">{choice.count.toLocaleString()}</span>
                </button>
              </li>
            );
          })}
          {scope.platforms.length === 0 && (
            <li className="px-2.5 py-2 text-xs text-zinc-500">Import saves from TikTok, YouTube, Instagram or Facebook to pick one.</li>
          )}
          <li className="mt-1 border-t border-zinc-100 px-2.5 pt-2 text-[11px] leading-snug text-zinc-400 dark:border-zinc-800">
            Import, Transcripts and Settings always cover every platform.
          </li>
        </ul>
      )}
    </div>
  );
}
