// Pick a collection: a button that opens a small searchable list with every
// collection in its folders (and space), instead of a long plain dropdown.
// Used for "Add to…", "Move to…" and "Choose another" in Unsorted.
import { useMemo, useRef, useState, type ReactNode } from "react";

import Popover from "../../components/Popover";
import { icons } from "../../components/icons";
import type { Collection, Space } from "../sorting/sortingApi";
import FolderIcon from "./FolderIcon";

export default function CollectionPicker({
  collections,
  spaces = [],
  onPick,
  exclude = [],
  label,
  children,
  className,
  suggested = [],
}: {
  collections: Collection[];
  spaces?: Space[];
  onPick: (collection: Collection) => void;
  exclude?: number[]; // already in these
  label: string; // what the list is for, for screen readers ("Add to a collection")
  children: ReactNode; // the button's text
  className?: string;
  suggested?: string[]; // names to show first (the AI's picks)
}) {
  const button = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [find, setFind] = useState("");

  const groups = useMemo(() => {
    const wanted = find.trim().toLowerCase();
    const shown = collections.filter(
      (c) => !exclude.includes(c.id) && (!wanted || c.path.toLowerCase().includes(wanted)),
    );
    const bySpace = new Map<number | undefined, Collection[]>();
    for (const collection of shown) {
      const list = bySpace.get(collection.space_id) ?? [];
      list.push(collection);
      bySpace.set(collection.space_id, list);
    }
    return [...bySpace.entries()].map(([spaceId, list]) => ({
      name: spaces.length > 1 ? spaces.find((s) => s.id === spaceId)?.name ?? null : null,
      list,
      flat: wanted !== "",
    }));
  }, [collections, spaces, exclude, find]);

  const top = suggested
    .map((name) => collections.find((c) => c.name.toLowerCase() === name.toLowerCase()))
    .filter((c): c is Collection => !!c && !exclude.includes(c.id));

  function pick(collection: Collection) {
    setOpen(false);
    setFind("");
    onPick(collection);
  }

  return (
    <>
      <button
        ref={button}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className={
          className ??
          "inline-flex items-center gap-1 rounded-full border border-dashed border-zinc-300 px-2.5 py-0.5 text-xs text-zinc-600 transition hover:border-indigo-400 hover:text-indigo-700 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-indigo-500 dark:hover:text-indigo-300"
        }
      >
        {children}
      </button>
      {open && (
        <Popover anchor={button.current} onClose={() => setOpen(false)} label={label} width={300}>
          <input
            autoFocus
            value={find}
            onChange={(event) => setFind(event.target.value)}
            placeholder="Find a collection…"
            aria-label="Find a collection"
            className="mb-1.5 w-full rounded-lg border border-zinc-200 bg-transparent px-2.5 py-1.5 text-sm outline-none focus:border-indigo-400 dark:border-zinc-700"
          />
          <div className="max-h-72 overflow-y-auto">
            {top.length > 0 && !find && (
              <Group name="The AI suggests">
                {top.map((collection) => (
                  <Row key={`s${collection.id}`} collection={collection} flat onPick={pick} />
                ))}
              </Group>
            )}
            {groups.map((group, index) => (
              <Group key={index} name={group.name}>
                {group.list.map((collection) => (
                  <Row key={collection.id} collection={collection} flat={group.flat} onPick={pick} />
                ))}
              </Group>
            ))}
            {groups.length === 0 && (
              <p className="px-2 py-3 text-center text-xs text-zinc-500">
                {collections.length ? "No collection matches." : "No collections yet. Make one on the Collections page."}
              </p>
            )}
          </div>
        </Popover>
      )}
    </>
  );
}

function Group({ name, children }: { name: string | null; children: ReactNode }) {
  return (
    <div className="py-0.5">
      {name && <p className="px-2 pb-0.5 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{name}</p>}
      <ul role="listbox">{children}</ul>
    </div>
  );
}

function Row({ collection, flat, onPick }: { collection: Collection; flat: boolean; onPick: (c: Collection) => void }) {
  const folders = collection.path.split(" / ").slice(0, -1).join(" / ");
  return (
    <li role="option" aria-selected={false}>
      <button
        type="button"
        onClick={() => onPick(collection)}
        className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-zinc-100 focus-visible:bg-zinc-100 focus-visible:outline-none dark:hover:bg-zinc-800 dark:focus-visible:bg-zinc-800"
        style={flat ? undefined : { paddingLeft: 8 + collection.depth * 16 }}
      >
        <FolderIcon color={collection.color} icon={collection.icon} collectionId={collection.id} className="h-4 w-5" />
        <span className="min-w-0 flex-1 truncate">
          {collection.name}
          {flat && folders && <span className="ml-1.5 text-xs text-zinc-400">in {folders}</span>}
        </span>
        <span className="text-xs tabular-nums text-zinc-400">{collection.count}</span>
      </button>
    </li>
  );
}

export const pickerIcon = <span className="h-3.5 w-3.5">{icons.plus}</span>;
