// A save's tags as chips: click one to see every save with it, × to take it
// off, and type in the box to add one (existing tags are suggested).
import { useEffect, useId, useState, type FormEvent } from "react";

import { errorText } from "../../lib/api";
import type { ItemCard } from "../sorting/sortingApi";
import { COLOR_DOTS, announceChange, organizeApi, type Tag } from "./organizeApi";

const SOURCE_NOTE: Record<string, string> = {
  user: "added by you",
  ai: "added by the AI",
  rule: "added by one of your rules",
  auto: "added because it's in no collection",
};

let knownTags: Promise<Tag[]> | null = null; // shared by every editor on the screen

export default function TagEditor({
  item,
  onChange,
  compact = false,
}: {
  item: ItemCard;
  onChange: (item: ItemCard) => void;
  compact?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(!compact);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    knownTags ??= organizeApi.tags().then((t) => t.tags).finally(() => window.setTimeout(() => (knownTags = null), 30_000));
    knownTags.then((tags) => setSuggestions(tags.map((t) => t.name))).catch(() => undefined);
  }, [open]);

  async function run(task: () => Promise<ItemCard>) {
    setError(null);
    try {
      onChange(await task());
      announceChange();
    } catch (e) {
      setError(errorText(e));
    }
  }

  function add(event: FormEvent) {
    event.preventDefault();
    const name = draft.trim().replace(/^#/, "");
    if (!name) return;
    setDraft("");
    run(() => organizeApi.tagItem(item.id, name));
  }

  const list = item.tag_list ?? item.tags.map((name, i) => ({ id: -i - 1, name, color: null, source: "ai" as const }));
  return (
    <div className="flex flex-wrap items-center gap-1.5" data-testid={`tags-${item.id}`}>
      {list.map((tag) => (
        <span
          key={tag.name}
          title={SOURCE_NOTE[tag.source]}
          className="inline-flex items-center gap-1 rounded-full bg-zinc-100 py-0.5 pl-2 pr-1 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
        >
          {tag.color && <span className={`h-1.5 w-1.5 rounded-full ${COLOR_DOTS[tag.color]}`} aria-hidden="true" />}
          <a href={`#/library?tag=${encodeURIComponent(tag.name)}`} className="hover:underline" draggable={false}>
            #{tag.name}
          </a>
          {tag.id > 0 && (
            <button
              type="button"
              aria-label={`Remove tag ${tag.name}`}
              onClick={() => run(() => organizeApi.untagItem(item.id, tag.id))}
              className="rounded-full px-1 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
            >
              ×
            </button>
          )}
        </span>
      ))}
      {open ? (
        <form onSubmit={add} className="inline-flex">
          <input
            list={listId}
            value={draft}
            maxLength={40}
            autoFocus={compact}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => compact && !draft && setOpen(false)}
            placeholder="+ tag"
            aria-label={`Add a tag to “${item.title ?? "this save"}”`}
            className="w-24 rounded-full border border-dashed border-zinc-300 bg-transparent px-2 py-0.5 text-xs outline-none focus:border-indigo-500 dark:border-zinc-700"
          />
          <datalist id={listId}>
            {suggestions.filter((name) => !item.tags.includes(name)).map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-full border border-dashed border-zinc-300 px-2 py-0.5 text-xs text-zinc-500 hover:border-zinc-400 dark:border-zinc-700 dark:text-zinc-400"
        >
          + tag
        </button>
      )}
      {error && <span className="w-full text-xs text-red-600 dark:text-red-400">{error}</span>}
    </div>
  );
}
