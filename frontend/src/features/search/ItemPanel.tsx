// A side panel with everything about one saved video: AI notes, key
// details, next steps and the full transcript, with the search words marked.
// Escape or the × closes it.
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Badge, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { formatDuration } from "../enrich/enrichApi";
import Highlighted from "./Highlighted";
import { markWords, searchApi, type ItemDetails } from "./searchApi";

export default function ItemPanel({
  itemId,
  words = [],
  onClose,
}: {
  itemId: number;
  words?: string[]; // words to mark in the transcript
  onClose: () => void;
}) {
  const [details, setDetails] = useState<ItemDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setDetails(null);
    setError(null);
    searchApi.item(itemId).then(setDetails).catch((e) => setError(errorText(e)));
  }, [itemId]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const item = details?.item;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-zinc-950/30" onClick={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={item?.title ?? "Saved video"}
        className="flex h-full w-full max-w-xl flex-col overflow-y-auto bg-white shadow-xl dark:bg-zinc-900"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="sticky top-0 flex items-start gap-3 border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-900">
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold leading-snug">{item?.title ?? (error ? "Couldn't open it" : "Loading…")}</h2>
            {item && (
              <p className="kw-tip mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                {[item.platform_name, item.author ? `@${item.author.replace(/^@/, "")}` : null, formatDuration(item.duration_s)]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            )}
            {item && (
              <a href={`#/item/${item.id}`} className="mt-1 inline-block text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                Open full page (steps checklist)
              </a>
            )}
          </div>
          <button
            ref={closeRef}
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-lg px-2.5 py-1 text-lg leading-none text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          >
            ×
          </button>
        </div>

        <div className="space-y-5 px-6 py-5 text-sm">
          {error && <Notice tone="error">{error}</Notice>}
          {item && (
            <>
              <div className="flex gap-4">
                {item.has_thumbnail && (
                  <img src={`/api/items/${item.id}/thumbnail`} alt="" className="h-36 w-24 shrink-0 rounded-lg object-cover" />
                )}
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap gap-1.5">
                    {item.kind_label && <Badge tone="indigo">{item.kind_label}</Badge>}
                    {item.collections.map((c) => (
                      <Badge key={c.id}>{c.name}</Badge>
                    ))}
                  </div>
                  {item.summary && <p className="text-zinc-700 dark:text-zinc-300">{item.summary}</p>}
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-block font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    Open on {item.platform_name} ↗
                  </a>
                </div>
              </div>
              {item.caption && item.caption !== item.title && (
                <Section title="Caption">
                  <p className="whitespace-pre-line text-zinc-700 dark:text-zinc-300">
                    <Highlighted segments={markWords(item.caption, words)} />
                  </p>
                </Section>
              )}
              {item.facts.length > 0 && (
                <Section title="Key details">
                  <ul className="list-disc space-y-1 pl-4 text-zinc-700 dark:text-zinc-300">
                    {item.facts.map((fact) => (
                      <li key={fact}>{fact}</li>
                    ))}
                  </ul>
                </Section>
              )}
              {item.steps.length > 0 && (
                <Section title="Next steps">
                  <ol className="list-decimal space-y-1 pl-4 text-zinc-700 dark:text-zinc-300">
                    {item.steps.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                </Section>
              )}
              <Section title="Transcript">
                {details?.transcript ? (
                  <p className="whitespace-pre-line leading-relaxed text-zinc-700 dark:text-zinc-300" data-testid="transcript">
                    <Highlighted segments={markWords(details.transcript, words)} />
                  </p>
                ) : (
                  <p className="text-zinc-500">
                    {details?.transcript === "" ? "No speech in this video." : "No transcript yet. Make one on the Sort page."}
                  </p>
                )}
              </Section>
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</h3>
      {children}
    </section>
  );
}
