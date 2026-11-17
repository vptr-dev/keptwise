// One saved video in search results or chat: thumbnail, title, and why it
// was found (the matching words, highlighted, and where; or the passage
// that means something similar). Click it to see everything.
import { Badge } from "../../components/ui";
import { formatDuration } from "../enrich/enrichApi";
import type { ItemCard } from "../sorting/sortingApi";
import Highlighted from "./Highlighted";
import { whereIn, type SearchResult } from "./searchApi";

export default function ResultCard({
  item,
  result,
  number,
  onOpen,
}: {
  item: ItemCard;
  result?: SearchResult; // search results say why they were found
  number?: number; // chat sources show their [n]
  onOpen: (id: number) => void;
}) {
  const meta = [item.platform_name, item.author ? `@${item.author.replace(/^@/, "")}` : null, formatDuration(item.duration_s)]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      onClick={() => onOpen(item.id)}
      className="flex w-full gap-4 rounded-2xl border border-zinc-200 bg-white p-4 text-left shadow-sm transition hover:border-indigo-300 hover:shadow focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-indigo-700"
      data-testid={`result-${item.id}`}
    >
      <div className="h-20 w-14 shrink-0 overflow-hidden rounded-lg bg-zinc-100 dark:bg-zinc-800">
        {item.has_thumbnail && (
          <img src={`/api/items/${item.id}/thumbnail`} alt="" className="h-full w-full object-cover" loading="lazy" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {number != null && <Badge tone="indigo">[{number}]</Badge>}
          {item.kind_label && <Badge>{item.kind_label}</Badge>}
          {result?.found_by.includes("words") && <Badge tone="amber">Your words</Badge>}
          {result?.found_by.includes("similar") && <Badge tone="green">Similar idea</Badge>}
          <span className="text-xs text-zinc-500 dark:text-zinc-400">{meta}</span>
        </div>
        <p className="mt-1 truncate font-medium">{item.title ?? item.url}</p>
        {!result && item.summary && (
          <p className="mt-1 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-300">{item.summary}</p>
        )}
        {result?.matches.map((match) => (
          <p key={match.part} className="mt-1.5 text-sm text-zinc-700 dark:text-zinc-300">
            <span className="mr-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              {match.label}
              {whereIn(match.at_seconds) ? `, ${whereIn(match.at_seconds)}` : ""}:
            </span>
            <Highlighted segments={match.segments} />
          </p>
        ))}
        {result?.similar && !result.found_by.includes("words") && (
          <p className="mt-1.5 line-clamp-2 text-sm text-zinc-700 dark:text-zinc-300">
            <span className="mr-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              {result.similar.label}
              {whereIn(result.similar.at_seconds) ? `, ${whereIn(result.similar.at_seconds)}` : ""}:
            </span>
            {result.similar.text}
          </p>
        )}
        {result && result.words.length > 0 && (
          <p className="mt-1.5 text-xs text-zinc-500 dark:text-zinc-400">Matched: {result.words.join(", ")}</p>
        )}
      </div>
    </button>
  );
}
