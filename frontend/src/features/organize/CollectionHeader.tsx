// The top of one collection on the Collections screen: rename, colour, what
// goes in it (the AI reads this), whether the AI may file saves here, merge
// it into another one, delete it, and AI tools for what's inside.
import { useEffect, useState, type FormEvent } from "react";

import { icons } from "../../components/icons";
import { Button, inputClass } from "../../components/ui";
import { navigate } from "../../lib/router";
import { sortingApi, type Collection } from "../sorting/sortingApi";
import { IconPicker, readPicture } from "./collectionIcons";
import { COLOR_DOTS, COLORS, organizeApi, type CollectionChange } from "./organizeApi";

export default function CollectionHeader({
  collection,
  all,
  count,
  act,
  onDeleted,
}: {
  collection: Collection;
  all: Collection[];
  count: number;
  act: (task: () => Promise<unknown>) => void;
  onDeleted: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(collection.name);
  const [about, setAbout] = useState(collection.description ?? "");
  const [confirming, setConfirming] = useState(false);
  const [merging, setMerging] = useState(false);

  useEffect(() => {
    setAbout(collection.description ?? "");
    setEditing(false);
    setConfirming(false);
    setMerging(false);
  }, [collection.id, collection.description]);

  const change = (update: CollectionChange) => act(() => organizeApi.changeCollection(collection.id, update));
  const others = all.filter((c) => c.id !== collection.id);

  function rename(event: FormEvent) {
    event.preventDefault();
    setEditing(false);
    if (draft.trim() && draft.trim() !== collection.name) change({ name: draft.trim() });
  }

  const tool = (id: string) => navigate(`/chat?tool=${id}&collection=${collection.id}`);

  return (
    <div className="space-y-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex flex-wrap items-center gap-3">
        <span className={`h-3.5 w-3.5 rounded-full ${collection.color ? COLOR_DOTS[collection.color] : "bg-zinc-300 dark:bg-zinc-600"}`} aria-hidden="true" />
        {editing ? (
          <form onSubmit={rename} className="flex flex-1 gap-2">
            <input className={inputClass} aria-label="Collection name" autoFocus maxLength={80} value={draft} onChange={(e) => setDraft(e.target.value)} />
            <Button type="submit">Save</Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>
              Cancel
            </Button>
          </form>
        ) : (
          <>
            <h2 className="text-xl font-semibold tracking-tight">{collection.name}</h2>
            <span className="text-sm text-zinc-500">
              {count.toLocaleString()} save{count === 1 ? "" : "s"}
            </span>
            <div className="ml-auto flex flex-wrap gap-1">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setDraft(collection.name);
                  setEditing(true);
                }}
              >
                Rename
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setMerging(!merging)} disabled={others.length === 0}>
                Merge…
              </Button>
              {confirming ? (
                <>
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() =>
                      act(async () => {
                        await sortingApi.deleteCollection(collection.id);
                        onDeleted();
                      })
                    }
                  >
                    Delete “{collection.name}”
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setConfirming(false)}>
                    Keep it
                  </Button>
                </>
              ) : (
                <Button size="sm" variant="ghost" onClick={() => setConfirming(true)}>
                  Delete…
                </Button>
              )}
            </div>
          </>
        )}
      </div>
      {confirming && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">Its saves stay in the app; they just won't be in this collection any more.</p>
      )}
      {merging && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-zinc-50 p-3 text-sm dark:bg-zinc-800/60">
          <span>Move all of its saves into</span>
          <select
            aria-label="Merge into"
            defaultValue=""
            className="rounded-lg border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
            onChange={(e) => {
              const into = Number(e.target.value);
              if (into) act(async () => {
                await organizeApi.mergeCollection(collection.id, into);
                navigate(`/collections/${into}`);
              });
            }}
          >
            <option value="">pick a collection…</option>
            {others.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <span className="text-zinc-500">and delete “{collection.name}”.</span>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-[1fr_auto]">
        <label className="block">
          <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">What goes in it</span>
          <textarea
            className={`${inputClass} mt-1.5 min-h-16`}
            maxLength={300}
            placeholder="e.g. recipes and food places, not restaurant reviews. The AI reads this when it sorts."
            value={about}
            onChange={(e) => setAbout(e.target.value)}
            onBlur={() => about.trim() !== (collection.description ?? "") && change({ description: about.trim() })}
          />
        </label>
        <div className="space-y-3">
          <div>
            <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">Colour</p>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {COLORS.map((color) => (
                <button
                  key={color}
                  type="button"
                  aria-label={`Colour ${color}`}
                  aria-pressed={collection.color === color}
                  onClick={() => change({ color })}
                  className={`h-5 w-5 rounded-full ${COLOR_DOTS[color]} ${collection.color === color ? "ring-2 ring-zinc-900 ring-offset-1 dark:ring-white dark:ring-offset-zinc-900" : ""}`}
                />
              ))}
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">Icon</p>
            <div className="mt-1.5">
              <IconPicker
                value={collection.icon}
                onPick={(icon) => change({ icon: icon ?? "" })}
                onUpload={(file) => act(async () => organizeApi.uploadCollectionIcon(collection.id, await readPicture(file)))}
              />
              <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">Upload a PNG, JPG, WebP or GIF of your own, or pick one of these.</p>
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
            <input type="checkbox" checked={collection.ai_allowed} onChange={(e) => change({ ai_allowed: e.target.checked })} />
            The AI can sort saves into it
          </label>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-zinc-100 pt-3 text-sm dark:border-zinc-800">
        <span className="flex items-center gap-1.5 text-zinc-500">
          <span className="h-4 w-4 text-indigo-500">{icons.sparkle}</span>
          AI Assistant:
        </span>
        <Button size="sm" variant="secondary" onClick={() => tool("summary")} disabled={count === 0}>
          Summarise
        </Button>
        <Button size="sm" variant="secondary" onClick={() => tool("plan")} disabled={count === 0}>
          Make a plan
        </Button>
        <Button size="sm" variant="secondary" onClick={() => tool("shopping")} disabled={count === 0}>
          Shopping list
        </Button>
        <Button size="sm" variant="secondary" onClick={() => tool("compare")} disabled={count === 0}>
          Help me choose
        </Button>
        <a href={`#/library?collection_id=${collection.id}`} className="ml-auto text-indigo-600 hover:underline dark:text-indigo-400">
          Open in the Library
        </a>
      </div>
    </div>
  );
}
