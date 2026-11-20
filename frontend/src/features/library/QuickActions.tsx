// The quick buttons on a save's card (shown when the mouse is over it):
// tags, collection, plan and unsave, each in a small pop-up, so a save can
// be organised without opening it.
import { useEffect, useState, type FormEvent, type MouseEvent, type ReactNode } from "react";

import Popover from "../../components/Popover";
import { icons } from "../../components/icons";
import { inputClass } from "../../components/ui";
import { errorText } from "../../lib/api";
import { plansApi, type PlanSummary } from "../plans/plansApi";
import { COLOR_DOTS, TAGS_PER_SAVE, announceChange, organizeApi, type Tag } from "../organize/organizeApi";
import { COLLECTION_LIMIT, COLLECTIONS_PER_SAVE, sortingApi, type Collection, type ItemCard } from "../sorting/sortingApi";
import { libraryApi, type LibraryItem } from "./libraryApi";

type Panel = "tags" | "collection" | "plan";

const BUTTON =
  "flex h-7 w-7 items-center justify-center rounded-full bg-white/95 p-1.5 text-zinc-700 shadow ring-1 ring-black/5 transition hover:bg-indigo-600 hover:text-white focus-visible:outline-2 focus-visible:outline-indigo-500 dark:bg-zinc-900/95 dark:text-zinc-200";

const ROW =
  "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:text-zinc-200 dark:hover:bg-zinc-800";

function stop(event: MouseEvent) {
  event.preventDefault();
  event.stopPropagation();
}

export default function QuickActions({
  item,
  onChange,
  visible,
  inline = false,
}: {
  item: LibraryItem;
  onChange: (item: LibraryItem) => void;
  visible: boolean; // the mouse is over the card (or a pop-up is open)
  inline?: boolean;
}) {
  const [panel, setPanel] = useState<{ kind: Panel; anchor: HTMLElement } | null>(null);
  const open = (kind: Panel) => (event: MouseEvent<HTMLButtonElement>) => {
    stop(event);
    const anchor = event.currentTarget;
    setPanel((now) => (now?.kind === kind ? null : { kind, anchor }));
  };
  const close = () => setPanel(null);
  const changed = (card: ItemCard | LibraryItem) => {
    onChange({ ...item, ...card } as LibraryItem);
    announceChange();
  };

  const buttons: { kind: Panel; label: string; icon: ReactNode }[] = [
    { kind: "tags", label: "Tags", icon: icons.tag },
    { kind: "collection", label: "Collection", icon: icons.folder },
    { kind: "plan", label: "Add to a plan", icon: icons.plans },
  ];

  return (
    <>
      <div
        className={`flex shrink-0 gap-1.5 transition ${inline ? "flex-wrap" : "absolute right-2 top-2 flex-col"} ${
          visible || panel ? "opacity-100" : "pointer-events-none opacity-0 group-focus-within:pointer-events-auto group-focus-within:opacity-100"
        }`}
      >
        {buttons.map((button) => (
          <button
            key={button.kind}
            type="button"
            className={`${BUTTON} ${panel?.kind === button.kind ? "!bg-indigo-600 !text-white" : ""}`}
            aria-label={`${button.label} for this save`}
            title={button.label}
            onClick={open(button.kind)}
          >
            {button.icon}
          </button>
        ))}
      </div>
      {panel?.kind === "tags" && (
        <Popover anchor={panel.anchor} onClose={close} label="Tags">
          <TagsPanel item={item} onChange={changed} />
        </Popover>
      )}
      {panel?.kind === "collection" && (
        <Popover anchor={panel.anchor} onClose={close} label="Collections">
          <CollectionPanel item={item} onChange={changed} />
        </Popover>
      )}
      {panel?.kind === "plan" && (
        <Popover anchor={panel.anchor} onClose={close} label="Plans">
          <PlanPanel item={item} onChange={changed} />
        </Popover>
      )}
    </>
  );
}

function PanelTitle({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="px-2 pb-1.5 pt-1">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{children}</p>
      {hint && <p className="mt-0.5 text-[11px] text-zinc-400">{hint}</p>}
    </div>
  );
}

function Problem({ text }: { text: string | null }) {
  return text ? <p className="px-2 py-1 text-xs text-red-600 dark:text-red-400">{text}</p> : null;
}

// ---------- tags ----------

export function TagsPanel({ item, onChange }: { item: LibraryItem; onChange: (card: ItemCard) => void }) {
  const [all, setAll] = useState<Tag[]>([]);
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const own = (item.tag_list ?? []).filter((t) => t.source !== "auto");
  const full = own.length >= TAGS_PER_SAVE;

  useEffect(() => {
    organizeApi.tags().then((t) => setAll(t.tags)).catch(() => undefined);
  }, []);

  async function run(task: () => Promise<ItemCard>) {
    setProblem(null);
    try {
      onChange(await task());
    } catch (e) {
      setProblem(errorText(e));
    }
  }

  function add(event: FormEvent) {
    event.preventDefault();
    const name = text.trim().replace(/^#/, "");
    if (!name) return;
    setText("");
    void run(() => organizeApi.tagItem(item.id, name));
  }

  const wanted = text.trim().replace(/^#/, "").toLowerCase();
  const suggestions = all
    .filter((t) => !item.tags.includes(t.name) && (!wanted || t.name.includes(wanted)))
    .slice(0, 6);

  return (
    <div onClick={(e) => e.stopPropagation()}>
      <PanelTitle hint={`${own.length} of ${TAGS_PER_SAVE} tags. Tags are the small details, like “pasta” or “lisbon”.`}>
        Tags
      </PanelTitle>
      {item.tag_list && item.tag_list.length > 0 && (
        <div className="flex flex-wrap gap-1 px-2 pb-2">
          {item.tag_list.map((tag) => (
            <span key={tag.id} className="inline-flex items-center gap-1 rounded-full bg-zinc-100 py-0.5 pl-2 pr-1 text-xs dark:bg-zinc-800">
              #{tag.name}
              {tag.source === "ai" && <span className="text-[10px] text-indigo-500" title="Added by the AI">AI</span>}
              <button
                type="button"
                aria-label={`Remove #${tag.name}`}
                className="flex h-4 w-4 items-center justify-center rounded-full text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-700"
                onClick={() => run(() => organizeApi.untagItem(item.id, tag.id))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}
      <form onSubmit={add} className="flex gap-1.5 px-1">
        <input
          className={`${inputClass} py-1.5`}
          placeholder={full ? "Remove a tag to add another" : "Add a tag"}
          aria-label="New tag"
          maxLength={40}
          autoFocus
          disabled={full}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </form>
      {!full && suggestions.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1 px-2 pb-1">
          {suggestions.map((tag) => (
            <button
              key={tag.id}
              type="button"
              className="rounded-full border border-zinc-200 px-2 py-0.5 text-xs text-zinc-600 hover:border-indigo-400 hover:text-indigo-700 dark:border-zinc-700 dark:text-zinc-300"
              onClick={() => run(() => organizeApi.tagItem(item.id, tag.name))}
            >
              #{tag.name}
            </button>
          ))}
        </div>
      )}
      <Problem text={problem} />
    </div>
  );
}

// ---------- collection ----------

export function CollectionPanel({ item, onChange }: { item: LibraryItem; onChange: (card: ItemCard) => void }) {
  const [list, setList] = useState<Collection[] | null>(null);
  const [limit, setLimit] = useState(COLLECTION_LIMIT);
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const inIds = new Set(item.collections.map((c) => c.id));
  const full = inIds.size >= COLLECTIONS_PER_SAVE;

  useEffect(() => {
    sortingApi
      .collections()
      .then((o) => {
        setList(o.collections);
        setLimit(o.limit ?? COLLECTION_LIMIT);
      })
      .catch((e) => setProblem(errorText(e)));
  }, []);

  async function toggle(collection: Collection) {
    setProblem(null);
    try {
      const card = inIds.has(collection.id)
        ? await sortingApi.removeFrom(item.id, collection.id)
        : await sortingApi.move(item.id, null, collection.id);
      onChange(card);
    } catch (e) {
      setProblem(errorText(e));
    }
  }

  const wanted = text.trim().toLowerCase();
  const shown = (list ?? []).filter((c) => !wanted || c.name.toLowerCase().includes(wanted));
  const exact = (list ?? []).find((c) => c.name.toLowerCase() === wanted);
  const room = list ? limit - list.length : 0;

  /** Enter: tick the collection with that name, or make it. */
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!wanted) return;
    if (exact) {
      setText("");
      return toggle(exact);
    }
    if (shown.length === 1) {
      setText("");
      return toggle(shown[0]);
    }
    setProblem(null);
    try {
      const made = await organizeApi.createCollection(text.trim());
      setList(made.collections);
      setText("");
      if (made.created_id) onChange(await sortingApi.move(item.id, null, made.created_id));
    } catch (e) {
      setProblem(errorText(e));
    }
  }

  return (
    <div>
      <PanelTitle hint={`In ${inIds.size} of up to ${COLLECTIONS_PER_SAVE}.`}>Collections</PanelTitle>
      <form onSubmit={submit} className="px-1 pb-1.5">
        <input
          className={`${inputClass} py-1.5`}
          placeholder={room > 0 ? "Find or make a collection" : "Find a collection"}
          aria-label="Find or make a collection"
          maxLength={80}
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </form>
      {list === null && !problem && <p className="px-2 py-1 text-xs text-zinc-500">Loading…</p>}
      <div className="max-h-64 overflow-y-auto">
        {shown.map((collection) => {
          const on = inIds.has(collection.id);
          return (
            <button
              key={collection.id}
              type="button"
              className={ROW}
              role="menuitemcheckbox"
              aria-checked={on}
              disabled={!on && full}
              title={!on && full ? `A save can be in up to ${COLLECTIONS_PER_SAVE} collections` : undefined}
              onClick={() => toggle(collection)}
            >
              <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border p-0.5 ${on ? "border-indigo-600 bg-indigo-600 text-white" : "border-zinc-300 text-transparent dark:border-zinc-600"}`}>
                {icons.check}
              </span>
              <span className={`h-2 w-2 shrink-0 rounded-full ${collection.color ? COLOR_DOTS[collection.color] : "bg-zinc-300 dark:bg-zinc-600"}`} />
              <span className="flex-1 truncate" style={{ paddingLeft: wanted ? 0 : collection.depth * 12 }} title={collection.path}>
                {wanted && collection.depth > 0 ? collection.path : collection.name}
              </span>
              <span className="text-xs tabular-nums text-zinc-400">{collection.count}</span>
            </button>
          );
        })}
      </div>
      {list && wanted && !exact && shown.length !== 1 && (
        <p className="mt-1 border-t border-zinc-100 px-2 pt-2 text-[11px] text-zinc-500 dark:border-zinc-800">
          {room > 0
            ? `Press Enter to make “${text.trim()}” (${room} left) and put this save in it.`
            : `You have ${limit} collections, the most allowed. Use tags for smaller topics.`}
        </p>
      )}
      {full && <p className="px-2 pt-1 text-[11px] text-zinc-500">This save is in {COLLECTIONS_PER_SAVE} collections, the most allowed.</p>}
      <Problem text={problem} />
    </div>
  );
}

// ---------- plan ----------

export function PlanPanel({ item, onChange }: { item: LibraryItem; onChange: (card: ItemCard) => void }) {
  const [list, setList] = useState<PlanSummary[] | null>(null);
  const [newName, setNewName] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const inIds = new Set((item.plans ?? []).map((p) => p.id));

  useEffect(() => {
    plansApi.list().then((l) => setList(l.plans)).catch((e) => setProblem(errorText(e)));
  }, []);

  async function refreshCard() {
    const page = await libraryApi.item(item.id);
    onChange(page.item);
  }

  async function toggle(plan: PlanSummary) {
    setProblem(null);
    try {
      if (inIds.has(plan.id)) await plansApi.removeItem(plan.id, item.id);
      else await plansApi.add(plan.id, [item.id]);
      await refreshCard();
      plansApi.list().then((l) => setList(l.plans)).catch(() => undefined);
    } catch (e) {
      setProblem(errorText(e));
    }
  }

  async function make(event: FormEvent) {
    event.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setProblem(null);
    try {
      await plansApi.create(name, [item.id]);
      setNewName("");
      await refreshCard();
      plansApi.list().then((l) => setList(l.plans)).catch(() => undefined);
    } catch (e) {
      setProblem(errorText(e));
    }
  }

  const open = (list ?? []).filter((p) => !p.done || inIds.has(p.id));
  return (
    <div>
      <PanelTitle hint="A plan can be just this save, or many saves to work through.">Plans</PanelTitle>
      {list === null && !problem && <p className="px-2 py-1 text-xs text-zinc-500">Loading…</p>}
      <div className="max-h-56 overflow-y-auto">
        {open.map((plan) => {
          const on = inIds.has(plan.id);
          return (
            <button key={plan.id} type="button" className={ROW} role="menuitemcheckbox" aria-checked={on} onClick={() => toggle(plan)}>
              <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border p-0.5 ${on ? "border-indigo-600 bg-indigo-600 text-white" : "border-zinc-300 text-transparent dark:border-zinc-600"}`}>
                {icons.check}
              </span>
              <span className="flex-1 truncate">{plan.name}</span>
              <span className="text-xs tabular-nums text-zinc-400">
                {plan.items_done}/{plan.item_count}
              </span>
            </button>
          );
        })}
      </div>
      <form onSubmit={make} className="mt-1 border-t border-zinc-100 px-1 pt-2 dark:border-zinc-800">
        <input
          className={`${inputClass} py-1.5`}
          placeholder="New plan with this save"
          aria-label="New plan name"
          maxLength={80}
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
      </form>
      <Problem text={problem} />
    </div>
  );
}
