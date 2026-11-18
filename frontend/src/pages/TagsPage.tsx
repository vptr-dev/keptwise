// Tags (#/tags): the small details on your saves ("pasta", "lisbon",
// "leg day"). Up to 100 in the app, up to 10 on each save. Right-click a tag
// for everything you can do with it. Find, sort and
// filter them (yours or the AI's), open one to see its saves, rename it
// (two tags with the same name become one), colour it, pick several to merge
// or delete at once, or let the AI tag the saves that have none.
import ColourPicker, { Swatch } from "../components/ColourPicker";
import Popover from "../components/Popover";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { useContextMenu } from "../components/ContextMenu";
import { useDialog } from "../components/Dialog";
import EmptyState from "../components/EmptyState";
import { icons } from "../components/icons";
import { Button, Card, Notice, Segmented, inputClass } from "../components/ui";
import { tagMenuItems } from "../features/organize/menus";
import {
  TAG_LIMIT,
  TAGS_PER_SAVE,
  announceChange,
  onOrganizeChange,
  organizeApi,
  type Tag,
} from "../features/organize/organizeApi";
import { sortingApi } from "../features/sorting/sortingApi";
import { errorText } from "../lib/api";
import { navigate } from "../lib/router";
import { Tip } from "../lib/tips";

type Order = "used" | "name" | "newest";
type Source = "all" | "mine" | "ai" | "unused";

export default function TagsPage() {
  const [tags, setTags] = useState<Tag[] | null>(null);
  const [limit, setLimit] = useState({ total: 0, limit: TAG_LIMIT });
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [order, setOrder] = useState<Order>("used");
  const [source, setSource] = useState<Source>("all");
  const [newTag, setNewTag] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [mergeName, setMergeName] = useState("");
  const [suggested, setSuggested] = useState(0);

  const load = useCallback(() => {
    organizeApi
      .tags()
      .then((t) => {
        setTags(t.tags);
        setLimit({ total: t.total ?? t.tags.length, limit: t.limit ?? TAG_LIMIT });
      })
      .catch((e) => setError(errorText(e)));
    sortingApi
      .overview()
      .then((o) => setSuggested(o.counts.tag_suggested ?? 0))
      .catch(() => undefined);
  }, []);
  useEffect(load, [load]);
  useEffect(() => onOrganizeChange(load), [load]);


  async function act(task: () => Promise<unknown>) {
    setError(null);
    try {
      await task();
    } catch (e) {
      setError(errorText(e));
    }
    announceChange();
  }

  function create(event: FormEvent) {
    event.preventDefault();
    const name = newTag.trim();
    if (!name) return;
    setNewTag("");
    act(() => organizeApi.createTag(name));
  }

  const wanted = filter.trim().replace(/^#/, "").toLowerCase();
  const shown = (tags ?? [])
    .filter((tag) => !wanted || tag.name.includes(wanted))
    .filter((tag) =>
      source === "mine" ? (tag.by_user ?? 0) > 0 : source === "ai" ? (tag.by_ai ?? 0) > 0 : source === "unused" ? tag.count === 0 : true,
    )
    .sort((a, b) =>
      order === "name"
        ? a.name.localeCompare(b.name)
        : order === "newest"
          ? (b.created_at ?? "").localeCompare(a.created_at ?? "") || b.id - a.id
          : b.count - a.count || a.name.localeCompare(b.name),
    );
  const pickedTags = (tags ?? []).filter((t) => picked.includes(t.id));
  const toggle = (id: number) => setPicked((old) => (old.includes(id) ? old.filter((p) => p !== id) : [...old, id]));
  const total = tags?.length ?? 0;
  const used = (tags ?? []).filter((t) => t.count > 0).length;
  const full = limit.total >= limit.limit;

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-8 py-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tags</h1>
          <p className="kw-tip text-sm text-zinc-500 dark:text-zinc-400">
            The small details on your saves. {total > 0 && `${total.toLocaleString()} tags, ${used.toLocaleString()} in use.`}{" "}
            <span className="tabular-nums" title={`The app allows up to ${limit.limit} tags`}>
              ({limit.total} of {limit.limit} used)
            </span>
          </p>
        </div>
      </header>

      {suggested > 0 && (
        <Notice>
          The AI suggests tags for {suggested.toLocaleString()} save{suggested === 1 ? "" : "s"}.{" "}
          <a href="#/transcripts" className="font-medium underline">
            Add them on the Sort page
          </a>
          .
        </Notice>
      )}

      <Tip id="tags-intro">
        Tags are for details, like “pasta”, “lisbon” or “leg day”. The app holds up to {limit.limit}, and each save can
        have up to {TAGS_PER_SAVE}. For broad topics like Food or Travel, use Collections. Right-click a tag to rename,
        colour, merge or delete it.
      </Tip>

      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="search"
            className={`${inputClass} max-w-56`}
            placeholder="Find a tag"
            aria-label="Find a tag"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          <Segmented
            label="Order"
            value={order}
            onChange={setOrder}
            options={[
              { value: "used", label: "Most used" },
              { value: "name", label: "A–Z" },
              { value: "newest", label: "Newest" },
            ]}
          />
          <select
            aria-label="Whose tags"
            value={source}
            onChange={(e) => setSource(e.target.value as Source)}
            className="rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
          >
            <option value="all">All tags</option>
            <option value="mine">Added by me</option>
            <option value="ai">Added by the AI</option>
            <option value="unused">Not on any save</option>
          </select>
          <form onSubmit={create} className="ml-auto flex gap-2">
            <input
              className={`${inputClass} w-36`}
              placeholder={full ? "All tags used" : "New tag"}
              title={full ? `You have ${limit.limit} tags, the most allowed. Merge or delete some to add more.` : undefined}
              aria-label="New tag name"
              maxLength={40}
              disabled={full}
              value={newTag}
              onChange={(e) => setNewTag(e.target.value)}
            />
            <Button type="submit" variant="secondary" disabled={full || !newTag.trim()}>
              Add
            </Button>
          </form>
        </div>
      </Card>

      {error && <Notice tone="error" onClose={() => setError(null)}>{error}</Notice>}

      {picked.length > 0 && (
        <div role="toolbar" aria-label="Picked tags" className="sticky top-2 z-10 flex flex-wrap items-center gap-2 rounded-2xl border border-indigo-200 bg-indigo-50/95 px-4 py-3 text-sm shadow dark:border-indigo-900 dark:bg-indigo-950/90">
          <span className="font-medium">{picked.length} picked</span>
          <form
            className="flex items-center gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              const into = mergeName.trim() || pickedTags[0]?.name;
              if (!into) return;
              setMergeName("");
              setPicked([]);
              act(() => organizeApi.mergeTags(picked, into));
            }}
          >
            <span>Merge into</span>
            <input
              className="w-36 rounded-lg border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              placeholder={pickedTags[0]?.name ?? "name"}
              aria-label="Merge the picked tags into"
              maxLength={40}
              value={mergeName}
              onChange={(e) => setMergeName(e.target.value)}
            />
            <Button size="sm" type="submit" disabled={picked.length < 2 && !mergeName.trim()}>
              Merge
            </Button>
          </form>
          <Button
            size="sm"
            variant="danger"
            onClick={() => {
              const ids = picked;
              setPicked([]);
              act(() => organizeApi.deleteTags(ids));
            }}
          >
            Delete {picked.length}
          </Button>
          <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setPicked([])}>
            Clear
          </Button>
        </div>
      )}

      {tags !== null && tags.length === 0 && (
        <EmptyState icon={icons.tag} title="No tags yet">
          Tags appear when the AI writes notes for your saves. You can also add your own above, or on any save.
        </EmptyState>
      )}
      {shown.length > 0 && (
        <ul className="divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900" aria-label="Tags">
          {shown.map((tag) => (
            <TagRow key={tag.id} tag={tag} all={tags ?? []} picked={picked.includes(tag.id)} onPick={() => toggle(tag.id)} act={act} />
          ))}
        </ul>
      )}
      {tags !== null && tags.length > 0 && shown.length === 0 && <p className="text-sm text-zinc-500">No tag matches.</p>}
    </div>
  );
}

function TagRow({
  tag,
  all,
  picked,
  onPick,
  act,
}: {
  tag: Tag;
  all: Tag[];
  picked: boolean;
  onPick: () => void;
  act: (task: () => Promise<unknown>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(tag.name);
  const [confirming, setConfirming] = useState(false);
  const [colours, setColours] = useState<HTMLElement | null>(null);
  const [openMenu, menu] = useContextMenu();
  const [ask, dialog] = useDialog();
  const pickItem = { label: picked ? "Unpick" : "Pick (to merge or delete several)", icon: icons.select, onSelect: onPick };

  return (
    <li
      className={`flex flex-wrap items-center gap-3 px-4 py-2.5 ${picked ? "bg-indigo-50/60 dark:bg-indigo-950/30" : ""}`}
      data-testid={`tag-${tag.name}`}
      onContextMenu={(event) => openMenu(event, tagMenuItems(tag, { all, ask, extra: [pickItem] }), `#${tag.name}`)}
    >
      {menu}
      {dialog}
      <input type="checkbox" checked={picked} onChange={onPick} aria-label={`Pick #${tag.name}`} />
      <button
        type="button"
        aria-label={`Colour of #${tag.name}`}
        onClick={(event) => setColours(colours ? null : event.currentTarget)}
        className="flex h-5 w-5 items-center justify-center rounded-full hover:bg-zinc-900/5 dark:hover:bg-white/10"
      >
        <Swatch colour={tag.color === "accent" ? null : tag.color} className="h-3.5 w-3.5" />
      </button>
      {colours && (
        <Popover anchor={colours} onClose={() => setColours(null)} label={`Colour of #${tag.name}`} width={232}>
          <ColourPicker
            value={tag.color}
            onPick={(color) => {
              setColours(null);
              act(() => organizeApi.changeTag(tag.id, { color: color ?? "accent" }));
            }}
          />
        </Popover>
      )}
      {editing ? (
        <form
          className="flex flex-1 gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setEditing(false);
            if (draft.trim() && draft.trim() !== tag.name) act(() => organizeApi.changeTag(tag.id, { name: draft.trim() }));
          }}
        >
          <input className={`${inputClass} py-1`} aria-label={`New name for #${tag.name}`} autoFocus maxLength={40} value={draft} onChange={(e) => setDraft(e.target.value)} />
          <Button type="submit" size="sm">Save</Button>
          <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
        </form>
      ) : (
        <a href={`#/library?tags=${encodeURIComponent(tag.name)}`} className="min-w-0 flex-1 truncate font-medium hover:text-indigo-600 dark:hover:text-indigo-400">
          #{tag.name}
        </a>
      )}
      {!editing && (
        <>
          <span className="text-sm tabular-nums text-zinc-500" title={`${tag.by_user ?? 0} by you, ${tag.by_ai ?? 0} by the AI, ${tag.by_app ?? 0} by your rules`}>
            {tag.count.toLocaleString()} save{tag.count === 1 ? "" : "s"}
            {(tag.by_ai ?? 0) > 0 && <span className="ml-1.5 text-[11px] text-indigo-500">AI {tag.by_ai}</span>}
          </span>
          {tag.count > 0 && (
            <Button size="sm" variant="ghost" onClick={() => navigate(`/chat?tool=summary&tag=${encodeURIComponent(tag.name)}`)} title="Ask the AI Assistant to summarise these saves">
              Summarise
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => { setDraft(tag.name); setEditing(true); }} title="Typing the name of another tag merges the two">
            Rename
          </Button>
          {confirming ? (
            <>
              <Button size="sm" variant="danger" onClick={() => act(() => organizeApi.deleteTag(tag.id))}>Delete #{tag.name}</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>Keep</Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>Delete</Button>
          )}
        </>
      )}
    </li>
  );
}
