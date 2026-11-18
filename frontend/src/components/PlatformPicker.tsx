// The drop-down at the top left: which platform's saves to manage. "All" is
// the default; then each platform that has saves. Plain words, no logos. The
// list floats above everything (it used to slide under the page in the slim
// sidebar).
import { useState } from "react";

import type { Scope } from "../lib/scope";
import { icons } from "./icons";
import Popover from "./Popover";

const SHORT: Record<string, string> = { tiktok: "TT", youtube: "YT", instagram: "IG", facebook: "FB" };

export default function PlatformPicker({
  scope,
  onChoose,
  compact = false,
}: {
  scope: Scope;
  onChoose: (platform: string | null) => void;
  compact?: boolean;
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const current = scope.platforms.find((p) => p.id === scope.platform);
  const label = current ? current.label : "All";
  const short = current ? (SHORT[current.id] ?? current.label.slice(0, 2)) : "All";

  function pick(platform: string | null) {
    setAnchor(null);
    if (platform !== scope.platform) onChoose(platform);
  }

  return (
    <>
      <button
        type="button"
        onClick={(event) => setAnchor(anchor ? null : event.currentTarget)}
        aria-haspopup="listbox"
        aria-expanded={!!anchor}
        aria-label={`Platform: ${label}. Change`}
        title={compact ? `Platform: ${label}` : "Which platform's saves to show"}
        className={`flex items-center rounded-xl border border-zinc-900/10 bg-white/50 text-sm font-medium text-zinc-800 transition hover:border-zinc-900/20 hover:bg-white/80 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:border-white/10 dark:bg-white/5 dark:text-zinc-100 dark:hover:border-white/20 dark:hover:bg-white/10 ${
          compact ? "mx-auto h-10 w-10 justify-center text-xs" : "h-9 w-full gap-2 px-3"
        }`}
      >
        {compact ? (
          short
        ) : (
          <>
            <span className="flex-1 truncate text-left">{label}</span>
            <span className="h-3.5 w-3.5 text-zinc-400">{icons.down}</span>
          </>
        )}
      </button>
      {anchor && (
        <Popover anchor={anchor} onClose={() => setAnchor(null)} label="Platform" width={220}>
          <ul role="listbox" aria-label="Platform">
            {[{ id: null as string | null, label: "All", count: scope.total }, ...scope.platforms].map((choice) => {
              const selected = choice.id === scope.platform;
              return (
                <li key={choice.id ?? "all"} role="option" aria-selected={selected}>
                  <button
                    type="button"
                    onClick={() => pick(choice.id)}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm ${
                      selected ? "bg-zinc-900/5 font-medium dark:bg-white/10" : "hover:bg-zinc-900/5 dark:hover:bg-white/5"
                    }`}
                  >
                    <span className="flex-1">{choice.label}</span>
                    <span className="text-xs tabular-nums text-zinc-400">{choice.count.toLocaleString()}</span>
                    <span className="h-4 w-4 text-zinc-500">{selected ? icons.check : null}</span>
                  </button>
                </li>
              );
            })}
            {scope.platforms.length === 0 && (
              <li className="px-2.5 py-2 text-xs text-zinc-500">Import saves from TikTok, YouTube, Instagram or Facebook to pick one.</li>
            )}
            <li className="kw-tip mt-1 border-t border-zinc-900/5 px-2.5 pt-2 text-[11px] leading-snug text-zinc-400 dark:border-white/10">
              Import, Sort and Settings always cover every platform.
            </li>
          </ul>
        </Popover>
      )}
    </>
  );
}
