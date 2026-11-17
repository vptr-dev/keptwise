// The two ways to tag, at the top of the Tags page: let the AI do it, or do
// it by hand. The AI's choices open right here, not in Settings.
import { useState, type ReactNode } from "react";

import { icons } from "../../components/icons";
import { Button } from "../../components/ui";
import { TagOptions, useAiSwitch } from "../sorting/SortingSettings";

type Way = "ai" | "hand";

export default function TagChoices({
  untagged,
  tagged,
  busy,
  onTags,
}: {
  untagged: number | null; // saves with a transcript and no tags
  tagged: boolean; // some saves have notes, so "tag everything again" makes sense
  busy: boolean; // an AI tags job is running
  onTags: (which: "untagged" | "with_notes") => void;
}) {
  const [open, setOpen] = useState<Way | null>(null);
  const [auto, setAuto] = useAiSwitch("auto_tag");
  const none = untagged ?? 0;

  const ways: { id: Way; icon: ReactNode; title: string; status: string }[] = [
    {
      id: "ai",
      icon: icons.sparkle,
      title: "Let the AI tag",
      status: auto === null ? "…" : auto ? "On: new saves are tagged by themselves" : "Off: it only tags when you ask",
    },
    { id: "hand", icon: icons.tag, title: "Tag by hand", status: untagged === null ? "…" : `${none.toLocaleString()} save${none === 1 ? "" : "s"} without tags` },
  ];

  return (
    <section aria-label="Ways to tag" className="space-y-3">
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

      {open === "ai" && (
        <div className="kw-pop space-y-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
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
              <span className="block text-sm font-medium">Tag new saves by themselves</span>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                When the AI writes a save's notes, it also gives it a few broad tags, like “pasta” or “london”. It reuses
                the tags you already have, and never removes one you added.
              </span>
            </span>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={busy || none === 0} onClick={() => onTags("untagged")}>
              <span className="h-4 w-4">{icons.sparkle}</span>
              {none === 0 ? "Every save has tags" : `Tag the ${none.toLocaleString()} without tags`}
            </Button>
            <Button variant="secondary" disabled={busy || !tagged} onClick={() => onTags("with_notes")} title="Replaces the AI's tags on every save with notes. Your own tags stay.">
              Tag everything again
            </Button>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">A save counts here once it has a transcript.</span>
          </div>
          <details className="rounded-xl border border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <summary className="cursor-pointer text-sm font-medium">How the AI tags (how many, and which words)</summary>
            <div className="mt-4">
              <TagOptions />
            </div>
          </details>
        </div>
      )}

      {open === "hand" && (
        <div className="kw-pop space-y-3 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
          <ul className="grid gap-x-6 gap-y-1.5 text-sm text-zinc-700 sm:grid-cols-2 dark:text-zinc-300">
            <li>
              In the Library, <b>point at a save</b> and press the tag button, or right-click it and choose “Tags…”.
            </li>
            <li>
              <b>Pick several saves</b> with their boxes and use “Add tag” in the bar that appears.
            </li>
            <li>
              <b>Right-click a tag</b> below to rename, colour, merge or delete it.
            </li>
            <li>
              Make a tag before using it with <b>New tag</b>, below.
            </li>
          </ul>
          {auto && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              The AI is also tagging new saves. To do it all yourself, switch that off under “Let the AI tag”.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
