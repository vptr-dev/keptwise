// The Organise panel at the top of the Collections page: how to organise by
// hand, and bringing over the collections you made on TikTok, YouTube,
// Instagram or Facebook. The AI isn't here: everything it does is on the
// Sort page.
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { icons } from "../../components/icons";
import { Button, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { navigate } from "../../lib/router";
import type { Collection, LibraryCounts, Space } from "../sorting/sortingApi";
import { announceChange, organizeApi, type PlatformLinks } from "./organizeApi";

export type Way = "hand" | "platforms";

export default function OrganiseChoices({
  counts,
  spaceId,
  spaceName,
  collections,
  spaces,
  inside,
  initial = null,
}: {
  counts: LibraryCounts | undefined;
  spaceId: number | undefined;
  spaceName: string;
  collections: Collection[];
  spaces: Space[];
  inside: Collection | undefined; // the collection that's open, if any
  initial?: Way | null;
}) {
  const [open, setOpen] = useState<Way | null>(initial);
  const [data, setData] = useState<PlatformLinks | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  useEffect(() => setOpen(initial), [initial]);
  const loadLinks = useCallback(() => {
    let current = true;
    setLoadError(null);
    organizeApi
      .platformLinks(spaceId)
      .then((result) => { if (current) setData(result); })
      .catch((error) => { if (current) setLoadError(errorText(error)); });
    return () => { current = false; };
  }, [spaceId]);
  useEffect(loadLinks, [loadLinks]);

  const unsorted = counts?.unsorted ?? 0;
  const ways: { id: Way; icon: ReactNode; title: string; status: string }[] = [
    { id: "hand", icon: icons.select, title: "Organise by hand", status: `${unsorted.toLocaleString()} in Unsorted` },
    {
      id: "platforms",
      icon: icons.link,
      title: "Bring from your platform",
      status: "Import destinations and collection links",
    },
  ];

  return (
    <section aria-label="Ways to organise" className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-2">
        {ways.map((way) => {
          const active = open === way.id;
          return (
            <button
              key={way.id}
              type="button"
              aria-expanded={active}
              onClick={() => setOpen(active ? null : way.id)}
              className={`flex items-center gap-3 rounded-2xl border px-4 py-3 text-left transition focus-visible:outline-2 focus-visible:outline-indigo-500 ${
                active
                  ? "border-indigo-400 bg-indigo-50 shadow-sm dark:border-indigo-700 dark:bg-indigo-950/40"
                  : "border-zinc-200 bg-white hover:border-zinc-300 hover:shadow-sm dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-zinc-700"
              }`}
            >
              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl p-2 ${active ? "bg-indigo-600 text-white" : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"}`}>
                {way.icon}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium">{way.title}</span>
                <span className="block truncate text-xs text-zinc-500 dark:text-zinc-400">{way.status}</span>
              </span>
              <span className={`h-4 w-4 shrink-0 text-zinc-400 transition-transform ${active ? "rotate-180" : ""}`}>{icons.down}</span>
            </button>
          );
        })}
      </div>

      {open === "hand" && (
        <Panel>
          <ul className="grid gap-x-6 gap-y-1.5 text-sm text-zinc-700 sm:grid-cols-2 dark:text-zinc-300">
            <li>
              <b>Drag</b> a save onto a collection to put it there.
            </li>
            <li>
              <b>Drag a collection</b> onto another one to put it inside, or onto the path above to move it back out.
            </li>
            <li>
              <b>Tick the boxes</b> (or Ctrl-click, Shift-click for a run) to pick several, then move them together.
            </li>
            <li>
              <b>Right-click</b> a collection or a save for everything you can do with it.
            </li>
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant={unsorted ? "primary" : "secondary"} onClick={() => navigate("/collections/unsorted")}>
              Unsorted ({unsorted.toLocaleString()})
            </Button>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              The AI's suggestions, and the switches for it, are on the{" "}
              <a href="#/transcripts" className="underline">
                Sort
              </a>{" "}
              page.
            </span>
          </div>
        </Panel>
      )}

      {open === "platforms" && (
        <Panel>
          {loadError && <Notice tone="error">{loadError} <Button onClick={loadLinks}>Retry</Button></Notice>}
          {data ? (
            <BringOver
              data={data}
              spaceId={spaceId}
              spaceName={spaceName}
              collections={collections}
              spaces={spaces}
              inside={inside}
              onDone={setData}
            />
          ) : !loadError && <p className="text-sm text-zinc-500">Loading…</p>}
        </Panel>
      )}
    </section>
  );
}

function Panel({ children }: { children: ReactNode }) {
  return (
    <div className="kw-pop space-y-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
      {children}
    </div>
  );
}

/** Your platform's collections, made here with the same names, in one go. */
function BringOver({
  data,
  spaceId,
  spaceName,
  collections,
  spaces,
  inside,
  onDone,
}: {
  data: PlatformLinks;
  spaceId: number | undefined;
  spaceName: string;
  collections: Collection[];
  spaces: Space[];
  inside: Collection | undefined;
  onDone: (data: PlatformLinks) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const { links, import_destinations: destinations = [] } = data;
  const todo = links.filter((l) => l.collection_id === null);
  const namesOnly = links.some((l) => !l.membership_known);
  const where = inside ? `inside “${inside.name}”` : `in ${spaceName}`;
  const options = collections.map((collection) => {
    const space = spaces.find((entry) => entry.id === collection.space_id);
    return <option key={collection.id} value={collection.id}>{space ? `${space.name} / ` : ""}{collection.path}</option>;
  });

  async function save(action: () => Promise<string>) {
    setBusy(true);
    setProblem(null);
    setMessage(null);
    try {
      setMessage(await action());
      announceChange();
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function transfer(): Promise<string> {
    const done = await organizeApi.transferPlatforms({ space_id: spaceId, parent_id: inside?.id ?? null });
    onDone(done);
    const made = done.made ?? 0;
    const reused = (done.linked ?? 0) - made;
    const parts = [
      made ? `Made ${made} collection${made === 1 ? "" : "s"} ${where}` : null,
      reused ? `${reused} already existed and ${reused === 1 ? "was" : "were"} kept` : null,
      done.filed ? `${done.filed.toLocaleString()} save${done.filed === 1 ? "" : "s"} put in them` : null,
    ].filter(Boolean);
    return `${parts.join(", ") || "Nothing new to bring over"}.${done.no_room ? ` ${done.no_room} didn't fit: this space is full.` : ""}`;
  }

  const selectClass = "w-full rounded-lg border border-zinc-300 bg-transparent px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900";
  return (
    <div className="space-y-4">
      {destinations.length > 0 && <section className="space-y-2" aria-label="New import destinations">
        <h3 className="text-sm font-semibold">Where new saves go</h3>
        <p className="text-xs text-zinc-600 dark:text-zinc-400">
          When an import has a matching collection link below, that link takes priority. Existing saves keep their placements.
          {collections.length === 0 && " Create a collection first to choose a destination."}
        </p>
        <div className="grid gap-2 sm:grid-cols-2">
          {destinations.map((destination) => (
            <label className="space-y-1 text-xs" key={destination.platform}>
              <span>{destination.platform_name}</span>
              <select className={selectClass} disabled={busy || collections.length === 0} value={destination.collection_id ?? ""}
                onChange={(event) => {
                  const id = Number(event.target.value) || null;
                  void save(async () => {
                    const updated = await organizeApi.setImportDestination(destination.platform, id);
                    onDone({ ...data, ...updated });
                    return `${destination.platform_name} import destination updated.`;
                  });
                }}>
                <option value="">No default collection</option>
                {options}
              </select>
            </label>
          ))}
        </div>
      </section>}
      <section className="space-y-2 border-t border-zinc-200 pt-4 dark:border-zinc-800" aria-label="Imported collection links">
        <h3 className="text-sm font-semibold">Collections from your exports</h3>
        {links.length === 0 && <p className="text-xs text-zinc-500">No platform collections found in your imports yet.</p>}
        {links.some((link) => link.membership_known) && <p className="text-xs text-zinc-600 dark:text-zinc-400">
          Linking an export collection adds its known saves to the destination. Existing placements stay.
        </p>}
        {namesOnly && <p className="text-xs text-zinc-600 dark:text-zinc-400">
          Some exports, including TikTok’s, list collection names only. You can use those names as folders or AI sorting hints.
        </p>}
        {links.length > 0 && <details>
          <summary className="cursor-pointer text-sm">Manage collection links ({links.length})</summary>
          <ul className="mt-2 divide-y divide-zinc-200 dark:divide-zinc-800">
            {links.map((link) => (
              <li className="grid items-center gap-2 py-2 sm:grid-cols-2" key={`${link.platform}-${link.name}`}>
                <div>
                  <p className="text-sm">{link.name}</p>
                  <p className="text-xs text-zinc-500">{link.platform_name} · {link.membership_known
                    ? `${link.count.toLocaleString()} saves${link.collection_id ? ` · ${link.filed.toLocaleString()} filed` : ""}`
                    : "Name only"}</p>
                </div>
                <div className="flex items-center gap-2">
                  <select className={selectClass} aria-label={`Destination for ${link.platform_name} ${link.name}`}
                    disabled={busy || collections.length === 0} value={link.collection_id ?? ""}
                    onChange={(event) => {
                      const id = Number(event.target.value) || null;
                      void save(async () => {
                        const result = await organizeApi.linkPlatform({
                          platform: link.platform, name: link.name, collection_id: id, mode: "auto",
                        });
                        onDone(result);
                        return id === null ? "Collection link removed. Existing placements were kept."
                          : result.filed ? `Filed ${result.filed.toLocaleString()} saves.` : "Collection link saved.";
                      });
                    }}>
                    <option value="">No linked collection</option>
                    {options}
                  </select>
                  {link.mode === "manual" && link.collection_id !== null && link.membership_known && (
                    <Button variant="secondary" size="sm" disabled={busy} onClick={() => void save(async () => {
                      const result = await organizeApi.applyPlatform(link.platform, link.name);
                      onDone(result);
                      return `Filed ${(result.filed ?? 0).toLocaleString()} saves.`;
                    })}>Add now</Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </details>}
        <div className="flex flex-wrap gap-2">
          {todo.length > 0 && <Button disabled={busy} onClick={() => void save(transfer)}>
            Make {todo.length} collection{todo.length === 1 ? "" : "s"} here
          </Button>}
          {message && namesOnly && <Button variant="secondary" onClick={() => navigate("/transcripts")}>Go to Sort</Button>}
        </div>
      </section>
      {message && (
        <Notice tone="success" onClose={() => setMessage(null)}>
          {message}
        </Notice>
      )}
      {problem && (
        <Notice tone="error" onClose={() => setProblem(null)}>
          {problem}
        </Notice>
      )}
    </div>
  );
}
