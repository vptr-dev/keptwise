// The Organise panel at the top of the Collections page: how to organise by
// hand, and bringing over the collections you made on TikTok, YouTube,
// Instagram or Facebook. The AI isn't here: everything it does is on the
// Sort page.
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { icons } from "../../components/icons";
import { Button, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { navigate } from "../../lib/router";
import type { Collection, LibraryCounts } from "../sorting/sortingApi";
import { announceChange, organizeApi, type PlatformLink } from "./organizeApi";

export type Way = "hand" | "platforms";

export default function OrganiseChoices({
  counts,
  spaceId,
  spaceName,
  inside,
  initial = null,
}: {
  counts: LibraryCounts | undefined;
  spaceId: number | undefined;
  spaceName: string;
  inside: Collection | undefined; // the collection that's open, if any
  initial?: Way | null;
}) {
  const [open, setOpen] = useState<Way | null>(initial);
  const [links, setLinks] = useState<PlatformLink[] | null>(null);
  useEffect(() => setOpen(initial), [initial]);
  const loadLinks = useCallback(() => {
    organizeApi
      .platformLinks(spaceId)
      .then((l) => setLinks(l.links))
      .catch(() => setLinks([]));
  }, [spaceId]);
  useEffect(loadLinks, [loadLinks]);

  const unsorted = counts?.unsorted ?? 0;
  const waiting = (links ?? []).filter((l) => l.collection_id === null);
  const ways: { id: Way; icon: ReactNode; title: string; status: string }[] = [
    { id: "hand", icon: icons.select, title: "Organise by hand", status: `${unsorted.toLocaleString()} in Unsorted` },
    {
      id: "platforms",
      icon: icons.link,
      title: "Bring from your platform",
      status:
        links === null
          ? "…"
          : links.length === 0
            ? "No platform collections in your imports"
            : waiting.length
              ? `${waiting.length} collection${waiting.length === 1 ? "" : "s"} to bring over`
              : "All brought over",
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
          <BringOver links={links} spaceId={spaceId} spaceName={spaceName} inside={inside} onDone={loadLinks} />
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
  links,
  spaceId,
  spaceName,
  inside,
  onDone,
}: {
  links: PlatformLink[] | null;
  spaceId: number | undefined;
  spaceName: string;
  inside: Collection | undefined;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  if (links === null) return <p className="text-sm text-zinc-500">Loading…</p>;
  if (links.length === 0) {
    return (
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Your imports didn't include any collections from TikTok, YouTube, Instagram or Facebook. Import your data again
        if you've made some since.
      </p>
    );
  }
  const todo = links.filter((l) => l.collection_id === null);
  const namesOnly = links.some((l) => !l.membership_known);
  const where = inside ? `inside “${inside.name}”` : `in ${spaceName}`;

  async function go() {
    setBusy(true);
    setProblem(null);
    setMessage(null);
    try {
      const done = await organizeApi.transferPlatforms({ space_id: spaceId, parent_id: inside?.id ?? null });
      const made = done.made ?? 0;
      const reused = (done.linked ?? 0) - made;
      const parts = [
        made ? `Made ${made} collection${made === 1 ? "" : "s"} ${where}` : null,
        reused ? `${reused} already existed and ${reused === 1 ? "was" : "were"} kept` : null,
        done.filed ? `${done.filed.toLocaleString()} save${done.filed === 1 ? "" : "s"} put in them` : null,
      ].filter(Boolean);
      setMessage(`${parts.join(", ") || "Nothing new to bring over"}.${done.no_room ? ` ${done.no_room} didn't fit: this space is full.` : ""}`);
      announceChange();
      onDone();
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-700 dark:text-zinc-300">
        Makes a collection here for each one you had on the platform, with the same name, {where}. Ones you already have
        are kept as they are.
      </p>
      {namesOnly && (
        <p className="kw-tip text-xs text-zinc-500 dark:text-zinc-400">
          TikTok's data only lists your collection names, not which videos are in each, so these start empty. Then go to
          Sort and press “Suggest again”: the AI suggests which saves go in them, and you accept.
        </p>
      )}
      <ul className="flex flex-wrap gap-1.5">
        {links.map((link) => (
          <li
            key={`${link.platform}-${link.name}`}
            className={`rounded-full px-2.5 py-1 text-xs ${
              link.collection_id === null
                ? "bg-indigo-50 text-indigo-800 dark:bg-indigo-950/50 dark:text-indigo-200"
                : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
            }`}
            title={link.collection_id === null ? `From ${link.platform_name}` : `Already here as ${link.collection_name}`}
          >
            {link.collection_id !== null && "✓ "}
            {link.name}
            {link.membership_known && link.count > 0 && <span className="opacity-70"> · {link.count}</span>}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <Button disabled={busy || todo.length === 0} onClick={() => void go()}>
          {busy ? "Making them…" : todo.length ? `Make ${todo.length} collection${todo.length === 1 ? "" : "s"} here` : "All brought over"}
        </Button>
        {message && namesOnly && (
          <Button variant="secondary" onClick={() => navigate("/transcripts")}>
            Go to Sort
          </Button>
        )}
      </div>
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
