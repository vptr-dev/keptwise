// The command centre: one box in the middle of the screen for everything.
// Open it with Ctrl+K, "/" or the Search button at the top of the sidebar.
// Type words to find saves, pages, collections, tags and creators, or start
// with a prefix to look in one place only:
//   #  tags          /  collections      @  creators
//   >  things to do  ?  ask the AI Assistant
// Up/Down choose, Enter opens, Esc closes.
import { SaveControls } from "../library/SaveControls";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { icons } from "../../components/icons";
import { displayTitle, libraryApi, DEFAULT_QUERY, type LibraryFilters, type LibraryItem } from "../library/libraryApi";
import Thumb from "../library/Thumb";
import { navigate } from "../../lib/router";

export type CommandAction = {
  id: string;
  label: string;
  icon: ReactNode;
  keys?: string; // a shortcut shown on the right
  words?: string; // more words it can be found by
  run: () => void;
};

type Row = {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon?: ReactNode;
  item?: LibraryItem;
  run: () => void;
};

export const PREFIXES: { key: string; name: string; what: string }[] = [
  { key: "#", name: "Tags", what: "saves with a tag" },
  { key: "/", name: "Collections", what: "open a collection" },
  { key: "@", name: "Creators", what: "saves from one creator" },
  { key: ">", name: "Actions", what: "things to do" },
  { key: "?", name: "Ask", what: "ask the AI Assistant" },
];

const TYPING_PAUSE_MS = 180;
const MOST = 7; // rows per group

/** Every word typed must be somewhere in the text. Earlier matches come first. */
export function matchScore(text: string, typed: string): number {
  const hay = text.toLowerCase();
  const words = typed.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return 1;
  let score = 0;
  for (const word of words) {
    const at = hay.indexOf(word);
    if (at < 0) return 0;
    score += at === 0 ? 3 : hay[at - 1] === " " ? 2 : 1;
  }
  return score;
}

function best<T>(list: T[], text: (entry: T) => string, typed: string, most = MOST): T[] {
  return list
    .map((entry, index) => ({ entry, score: matchScore(text(entry), typed), index }))
    .filter((r) => r.score > 0)
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, most)
    .map((r) => r.entry);
}

export default function CommandPalette({ actions, onClose }: { actions: CommandAction[]; onClose: () => void }) {
  const [text, setText] = useState("");
  const [filters, setFilters] = useState<LibraryFilters | null>(null);
  const [saves, setSaves] = useState<{ q: string; items: LibraryItem[]; total: number } | null>(null);
  const [at, setAt] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  const prefix = PREFIXES.find((p) => text.startsWith(p.key))?.key ?? "";
  const typed = (prefix ? text.slice(1) : text).trim();

  useEffect(() => {
    input.current?.focus();
    libraryApi.filters().then(setFilters).catch(() => undefined);
  }, []);

  // Saves that match the words, a moment after typing stops.
  useEffect(() => {
    if (prefix || typed.length < 2) {
      setSaves(null);
      return;
    }
    let stale = false;
    const timer = window.setTimeout(() => {
      libraryApi
        .items({ ...DEFAULT_QUERY, q: typed })
        .then((page) => !stale && setSaves({ q: typed, items: page.items.slice(0, 6), total: page.total }))
        .catch(() => !stale && setSaves({ q: typed, items: [], total: 0 }));
    }, TYPING_PAUSE_MS);
    return () => {
      stale = true;
      window.clearTimeout(timer);
    };
  }, [prefix, typed]);

  const rows = useMemo<Row[]>(() => {
    const go = (path: string) => () => navigate(path);
    const tags = (filters?.tags ?? []).map<Row>((t) => ({
      id: `tag-${t.id}`,
      group: "Tags",
      label: `#${t.label}`,
      hint: `${t.count.toLocaleString()} save${t.count === 1 ? "" : "s"}`,
      icon: icons.tag,
      run: go(`/library?${new URLSearchParams({ tag: String(t.label) })}`),
    }));
    const collections = (filters?.collections ?? []).map<Row>((c) => ({
      id: `collection-${c.id}`,
      group: "Collections",
      label: c.label,
      hint: `${c.count.toLocaleString()} save${c.count === 1 ? "" : "s"}`,
      icon: icons.folder,
      run: go(`/collections/${c.id}`),
    }));
    const creators = (filters?.creators ?? []).map<Row>((c) => ({
      id: `creator-${c.id}`,
      group: "Creators",
      label: c.label,
      hint: `${c.count.toLocaleString()} saves`,
      icon: icons.library,
      run: go(`/library?${new URLSearchParams({ creator: String(c.id) })}`),
    }));
    const doing = actions.map<Row & { words: string }>((a) => ({
      id: a.id,
      group: "Actions",
      label: a.label,
      hint: a.keys,
      icon: a.icon,
      words: `${a.label} ${a.words ?? ""}`,
      run: a.run,
    }));
    const ask: Row = {
      id: "ask",
      group: "AI Assistant",
      label: typed ? `Ask the AI: “${typed}”` : "Ask the AI Assistant…",
      icon: icons.sparkle,
      run: go(typed ? `/chat?${new URLSearchParams({ q: typed })}` : "/chat"),
    };

    if (prefix === "#") return best(tags, (r) => r.label.slice(1), typed, 40);
    if (prefix === "/") return best(collections, (r) => r.label, typed, 40);
    if (prefix === "@") return best(creators, (r) => r.label.replace(/^@/, ""), typed, 40);
    if (prefix === ">") return best(doing, (r) => r.words, typed, 40);
    if (prefix === "?") return [ask];
    if (!typed) return doing.slice(0, 12);

    const found: Row[] = [
      {
        id: "search",
        group: "Search",
        label: `Search everything for “${typed}”`,
        hint: "words and similar ideas",
        icon: icons.search,
        run: go(`/search?${new URLSearchParams({ q: typed })}`),
      },
    ];
    if (saves?.q === typed) {
      for (const item of saves.items)
        found.push({ id: `save-${item.id}`, group: `Saves (${saves.total.toLocaleString()})`, label: displayTitle(item), hint: item.kind_label ?? item.platform_name, item, run: go(`/item/${item.id}`) });
    }
    found.push(...best(doing, (r) => r.words, typed, 5));
    found.push(...best(collections, (r) => r.label, typed, 4));
    found.push(...best(tags, (r) => r.label.slice(1), typed, 4));
    found.push(...best(creators, (r) => r.label.replace(/^@/, ""), typed, 3));
    found.push(ask);
    return found;
  }, [actions, filters, prefix, typed, saves]);

  useEffect(() => setAt(0), [text]);
  const chosen = Math.min(at, Math.max(rows.length - 1, 0));
  useEffect(() => {
    list.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [chosen, rows]);

  function run(row: Row | undefined) {
    if (!row) return;
    onClose();
    row.run();
  }

  function onKey(event: React.KeyboardEvent) {
    if (event.key === "Enter" && event.target instanceof HTMLButtonElement) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setAt(rows.length ? (chosen + 1) % rows.length : 0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setAt(rows.length ? (chosen - 1 + rows.length) % rows.length : 0);
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(rows[chosen]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      if (text) setText("");
      else onClose();
    }
  }

  const mode = PREFIXES.find((p) => p.key === prefix);
  let lastGroup = "";
  return createPortal(
    <div className="kw-fade fixed inset-0 z-[65] flex items-start justify-center bg-zinc-950/30 px-4 pt-[14vh] dark:bg-black/50" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label="Command centre" className="kw-rise kw-glass-pop flex max-h-[68vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border" onKeyDown={onKey}>
        <div className="flex items-center gap-3 border-b border-zinc-900/10 px-4 dark:border-white/10">
          <span className="h-5 w-5 shrink-0 text-zinc-400">{mode?.key === "?" ? icons.sparkle : icons.search}</span>
          <input
            ref={input}
            role="combobox"
            aria-expanded="true"
            aria-controls="command-results"
            aria-activedescendant={rows[chosen] ? `command-${rows[chosen].id}` : undefined}
            aria-label="Search or type a command"
            autoComplete="off"
            spellCheck={false}
            className="h-14 min-w-0 flex-1 bg-transparent text-base text-zinc-900 placeholder:text-zinc-400 focus:outline-none dark:text-zinc-100"
            placeholder={mode ? `${mode.name}: ${mode.what}` : "Search your saves, or type a command…"}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <kbd className="rounded-md border border-zinc-900/10 px-1.5 py-0.5 text-[10px] text-zinc-500 dark:border-white/15">Esc</kbd>
        </div>

        {!text && (
          <div className="flex flex-wrap gap-1.5 border-b border-zinc-900/10 px-4 py-2.5 dark:border-white/10" aria-label="Prefixes">
            {PREFIXES.map((p) => (
              <button
                key={p.key}
                type="button"
                title={`${p.key} ${p.what}`}
                onClick={() => {
                  setText(p.key);
                  input.current?.focus();
                }}
                className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs text-zinc-600 transition hover:bg-zinc-900/5 dark:text-zinc-300 dark:hover:bg-white/10"
              >
                <kbd className="rounded border border-zinc-900/10 px-1 text-[11px] text-zinc-900 dark:border-white/15 dark:text-zinc-100">{p.key}</kbd>
                {p.name}
              </button>
            ))}
          </div>
        )}

        <div ref={list} id="command-results" role="listbox" aria-label="Results" className="min-h-0 flex-1 overflow-y-auto p-1.5">
          {rows.length === 0 && (
            <p className="px-3 py-6 text-center text-sm text-zinc-500">
              {prefix && !filters ? "Loading…" : `Nothing found${typed ? ` for “${typed}”` : ""}.`}
            </p>
          )}
          {rows.map((row, index) => {
            const heading = row.group !== lastGroup ? row.group : null;
            lastGroup = row.group;
            const active = index === chosen;
            return (
              <div key={row.id}>
                {heading && <p className="px-2.5 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{heading}</p>}
                <div
                  id={`command-${row.id}`}
                  role="option"
                  aria-selected={active}
                  onMouseMove={() => index !== chosen && setAt(index)}
                  onClick={() => run(row)}
                  className={`group flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                    active ? "bg-indigo-600 text-white" : "text-zinc-800 dark:text-zinc-200"
                  }`}
                >
                  {row.item ? (
                    <Thumb item={row.item} showDuration={false} className="h-9 w-7 shrink-0 rounded" />
                  ) : (
                    <span className={`h-4 w-4 shrink-0 ${active ? "" : "text-zinc-500"}`}>{row.icon}</span>
                  )}
                  <span className="min-w-0 flex-1 truncate">{row.label}</span>
                  {row.item && <SaveControls id={row.item.id} title={row.label} onChange={changed => {
                    setSaves(old => old && {...old, items: old.items.filter(i => i.id !== changed.id), total: Math.max(0, old.total - 1)});
                  }} />}
                  {row.hint && <span className={`shrink-0 text-xs ${active ? "opacity-80" : "text-zinc-500"}`}>{row.hint}</span>}
                </div>
              </div>
            );
          })}
        </div>

        <div className="flex items-center gap-3 border-t border-zinc-900/10 px-4 py-2 text-[11px] text-zinc-500 dark:border-white/10">
          <span>↑↓ choose</span>
          <span>Enter open</span>
          <span className="ml-auto">Ctrl K opens this from anywhere</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
