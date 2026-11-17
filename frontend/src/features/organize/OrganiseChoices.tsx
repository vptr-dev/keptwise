// The three ways to organise, at the top of the Collections page: let the AI
// file saves, do it by hand, or bring over the collections you already made
// on TikTok, YouTube, Instagram or Facebook. Each one opens its choices right
// here, so nothing about collections hides in Settings.
import { useEffect, useState, type ReactNode } from "react";

import { icons } from "../../components/icons";
import { Button, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { navigate } from "../../lib/router";
import { CollectionSortOptions, useAutoSort } from "../sorting/SortingSettings";
import type { Collection, LibraryCounts, NotesOverview } from "../sorting/sortingApi";
import PlatformLinks from "./PlatformLinks";
import { announceChange, organizeApi } from "./organizeApi";

export type Way = "ai" | "hand" | "platforms";

export default function OrganiseChoices({
  collections,
  counts,
  notes,
  busy,
  spaceId,
  spaceName,
  inside,
  initial = null,
  keepManual,
  onKeepManual,
  onSort,
}: {
  collections: Collection[];
  counts: LibraryCounts | undefined;
  notes: NotesOverview | null;
  busy: boolean; // an AI job is running
  spaceId: number | undefined;
  spaceName: string;
  inside: Collection | undefined; // the collection that's open, if any
  initial?: Way | null;
  keepManual: boolean;
  onKeepManual: (value: boolean) => void;
  onSort: (which: "all" | "unsorted") => void;
}) {
  const [open, setOpen] = useState<Way | null>(initial);
  const [auto, setAuto] = useAutoSort();
  const [links, setLinks] = useState<{ linked: number; total: number } | null>(null);
  useEffect(() => setOpen(initial), [initial]);
  useEffect(() => {
    organizeApi
      .platformLinks(spaceId)
      .then((l) => setLinks({ linked: l.links.filter((x) => x.collection_id !== null).length, total: l.links.length }))
      .catch(() => undefined);
  }, [spaceId, collections.length]);

  const unsorted = counts?.unsorted ?? 0;
  const review = counts?.review ?? 0;
  const waiting = notes?.counts.waiting ?? 0;

  const ways: { id: Way; icon: ReactNode; title: string; status: string }[] = [
    {
      id: "ai",
      icon: icons.sparkle,
      title: "Let the AI organise",
      status: auto === null ? "…" : auto ? "On: new saves are filed by themselves" : "Off: it only sorts when you ask",
    },
    { id: "hand", icon: icons.select, title: "Organise by hand", status: `${unsorted.toLocaleString()} not in a collection yet` },
    {
      id: "platforms",
      icon: icons.link,
      title: "Bring from your platforms",
      status: links ? (links.total ? `${links.linked} of ${links.total} platform collections linked` : "None found in your imports yet") : "…",
    },
  ];

  return (
    <section aria-label="Ways to organise" className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-3">
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

      {open === "ai" && (
        <Panel>
          <label className="flex items-start gap-3">
            <input
              type="checkbox"
              role="switch"
              className="mt-0.5 h-4 w-4 accent-indigo-600"
              checked={auto ?? true}
              disabled={auto === null}
              onChange={(e) => setAuto(e.target.checked)}
            />
            <span>
              <span className="block text-sm font-medium">File new saves by themselves</span>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                When the AI writes a save's notes, it also puts it in the collection that fits. It never makes new
                collections, and never moves a save you placed yourself.
              </span>
            </span>
          </label>
          {waiting > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-xl bg-zinc-50 px-3 py-2.5 text-sm dark:bg-zinc-800/50" data-testid="notes-waiting">
              <span className="flex-1">
                {waiting.toLocaleString()} save{waiting === 1 ? " has" : "s have"} a transcript and {waiting === 1 ? "is" : "are"} waiting for notes.
              </span>
              <Button size="sm" variant="secondary" onClick={() => navigate("/transcripts")}>
                Write them on the Transcripts page
              </Button>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={busy || unsorted === 0} onClick={() => onSort("unsorted")}>
              <span className="h-4 w-4">{icons.sparkle}</span>
              Sort the {unsorted.toLocaleString()} not in a collection
            </Button>
            <Button variant="secondary" disabled={busy || (counts?.processed ?? 0) === 0} onClick={() => onSort("all")}>
              Sort everything again
            </Button>
            <label className="flex items-center gap-1.5 text-xs text-zinc-600 dark:text-zinc-400">
              <input type="checkbox" checked={keepManual} onChange={(event) => onKeepManual(event.target.checked)} />
              Keep the ones I placed myself
            </label>
            <span className="ml-auto text-xs text-zinc-500">Using {notes?.ai_label ?? "…"}</span>
          </div>
          <details className="rounded-xl border border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-medium">How the AI sorts (options and your rules)</summary>
            <div className="mt-4">
              <CollectionSortOptions collections={collections} />
            </div>
          </details>
        </Panel>
      )}

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
              Not in a collection ({unsorted.toLocaleString()})
            </Button>
            <Button variant="secondary" onClick={() => navigate("/collections/review")}>
              Needs review ({review.toLocaleString()})
            </Button>
            {auto && (
              <span className="text-xs text-zinc-500 dark:text-zinc-400">
                The AI is also filing new saves. To do it all yourself, switch that off under “Let the AI organise”.
              </span>
            )}
          </div>
        </Panel>
      )}

      {open === "platforms" && (
        <Panel>
          <TransferAll spaceId={spaceId} spaceName={spaceName} inside={inside} pending={links ? links.total - links.linked : 0} />
          <PlatformLinks collections={collections} spaceId={spaceId} />
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

/** One button: every platform collection not linked yet becomes a collection here. */
function TransferAll({
  spaceId,
  spaceName,
  inside,
  pending,
}: {
  spaceId: number | undefined;
  spaceName: string;
  inside: Collection | undefined;
  pending: number;
}) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function go() {
    setBusy(true);
    setProblem(null);
    setMessage(null);
    try {
      const done = await organizeApi.transferPlatforms({ space_id: spaceId, parent_id: inside?.id ?? null });
      const parts = [
        `Linked ${done.linked ?? 0} platform collection${done.linked === 1 ? "" : "s"}`,
        done.made ? `made ${done.made} new collection${done.made === 1 ? "" : "s"}` : null,
        done.filed ? `filed ${done.filed.toLocaleString()} save${done.filed === 1 ? "" : "s"}` : null,
      ].filter(Boolean);
      setMessage(`${parts.join(", ")}.${done.no_room ? ` ${done.no_room} didn't fit: this space is full.` : ""}`);
      announceChange();
    } catch (e) {
      setProblem(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3 rounded-xl bg-zinc-50 px-4 py-3 dark:bg-zinc-800/50">
        <div className="min-w-56 flex-1 text-sm">
          <p className="font-medium">Transfer them all automatically</p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            Every collection from your platforms that isn't linked yet gets a collection of the same name{" "}
            {inside ? `inside “${inside.name}”` : `in ${spaceName}`}, and its saves are filed there now and after each
            import. Ones you've already linked stay as they are.
          </p>
        </div>
        <Button disabled={busy || pending === 0} onClick={() => void go()}>
          {busy ? "Transferring…" : pending ? `Transfer ${pending} now` : "All transferred"}
        </Button>
      </div>
      {message && <Notice tone="success" onClose={() => setMessage(null)}>{message}</Notice>}
      {problem && <Notice tone="error" onClose={() => setProblem(null)}>{problem}</Notice>}
    </div>
  );
}
