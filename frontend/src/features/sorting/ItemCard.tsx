// One saved video as a card: thumbnail, AI title and summary, its
// collections and tags, and the notes and steps when opened. Drag it onto a
// collection in the sidebar to move it (or use "Move to…" from the keyboard).
import { useState, type DragEvent, type ReactNode } from "react";

import { useContextMenu } from "../../components/ContextMenu";
import { useDialog } from "../../components/Dialog";
import { Badge, Card } from "../../components/ui";
import type { LibraryItem } from "../library/libraryApi";
import { saveMenuItems } from "../library/saveMenu";
import { formatDuration } from "../enrich/enrichApi";
import TagEditor from "../organize/TagEditor";
import { DRAG_TYPE, type Collection, type ItemCard as Item, type ItemLink } from "./sortingApi";

const SOURCE_LABELS: Record<ItemLink["source"], string> = {
  user: "you",
  rule: "your rule",
  ai: "AI",
  platform: "from the platform",
};

/** The AI's word for a score (backend prompts.FIT_SCORES). */
export function fitWord(score: number): string {
  if (score >= 0.9) return "clear";
  if (score >= 0.7) return "likely";
  return score >= 0.45 ? "maybe" : "guess";
}

export default function ItemCard({
  item,
  collections,
  fromId,
  onMove,
  onRemove,
  onChange,
  actions,
}: {
  item: Item;
  collections: Collection[];
  fromId: number | null; // the collection this card is shown in, if any
  onMove: (toId: number) => void;
  onRemove: (collectionId: number) => void;
  onChange?: (item: Item) => void; // its tags changed
  actions?: ReactNode; // extra buttons (used by Needs review)
}) {
  const [open, setOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [openMenu, menu] = useContextMenu();
  const [ask, dialog] = useDialog();
  const from = fromId !== null ? collections.find((c) => c.id === fromId) : undefined;

  function startDrag(event: DragEvent) {
    event.dataTransfer.setData(DRAG_TYPE, JSON.stringify({ itemId: item.id, fromId }));
    event.dataTransfer.effectAllowed = "move";
    setDragging(true);
  }

  const meta = [item.platform_name, item.author ? `@${item.author.replace(/^@/, "")}` : null, formatDuration(item.duration_s)]
    .filter(Boolean)
    .join(" · ");

  return (
    <div
      draggable
      onDragStart={startDrag}
      onDragEnd={() => setDragging(false)}
      className={`cursor-grab transition active:cursor-grabbing ${dragging ? "opacity-50" : ""}`}
      data-testid={`item-${item.id}`}
      onContextMenu={(event) =>
        openMenu(
          event,
          saveMenuItems(item, {
            ask,
            from: from ? { id: from.id, name: from.name } : null,
            onChange: (changed: LibraryItem) => onChange?.(changed),
          }),
          item.title ?? undefined,
        )
      }
    >
      {menu}
      {dialog}
      <Card className="p-4">
        <div className="flex gap-4">
          <div className="h-24 w-16 shrink-0 overflow-hidden rounded-lg bg-zinc-100 dark:bg-zinc-800">
            {item.has_thumbnail && (
              <img src={`/api/items/${item.id}/thumbnail`} alt="" className="h-full w-full object-cover" loading="lazy" draggable={false} />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {item.kind_label && <Badge tone="indigo">{item.kind_label}</Badge>}
              <span className="text-xs text-zinc-500 dark:text-zinc-400">{meta}</span>
            </div>
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="mt-1 block truncate font-medium hover:underline"
              title={item.caption ?? item.url}
              draggable={false}
            >
              {item.title ?? item.url}
            </a>
            {item.summary && <p className="mt-1 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-300">{item.summary}</p>}
            {item.error && <p className="mt-1 text-sm text-red-700 dark:text-red-300">{item.error}</p>}

            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {item.collections.map((link) => (
                <span
                  key={link.id}
                  className="inline-flex items-center gap-1 rounded-full bg-zinc-100 py-0.5 pl-2.5 pr-1 text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                  title={`Put here by ${SOURCE_LABELS[link.source]}${link.confidence != null && link.source === "ai" ? ` (fit: ${fitWord(link.confidence)})` : ""}`}
                >
                  {link.name}
                  <button
                    type="button"
                    aria-label={`Take out of ${link.name}`}
                    className="rounded-full px-1 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
                    onClick={() => onRemove(link.id)}
                  >
                    ×
                  </button>
                </span>
              ))}
              <select
                aria-label={`Move “${item.title ?? "this video"}” to`}
                className="rounded-full border border-dashed border-zinc-300 bg-transparent px-2 py-0.5 text-xs text-zinc-500 hover:border-zinc-400 dark:border-zinc-700 dark:text-zinc-400"
                value=""
                onChange={(event) => event.target.value && onMove(Number(event.target.value))}
              >
                <option value="">{fromId === null ? "Add to…" : "Move to…"}</option>
                {collections.map((collection) => (
                  <option key={collection.id} value={collection.id}>
                    {" ".repeat((collection.depth ?? 0) * 2)}
                    {collection.name}
                  </option>
                ))}
              </select>
              {(item.facts.length > 0 || item.steps.length > 0) && (
                <button
                  type="button"
                  className="ml-auto text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                  aria-expanded={open}
                  onClick={() => setOpen(!open)}
                >
                  {open ? "Hide notes" : "Show notes"}
                </button>
              )}
            </div>
            {onChange && (
              <div className="mt-2">
                <TagEditor item={item} onChange={onChange} compact />
              </div>
            )}
            {actions && <div className="mt-3">{actions}</div>}
          </div>
        </div>
        {open && <Notes item={item} />}
      </Card>
    </div>
  );
}

function Notes({ item }: { item: Item }) {
  return (
    <div className="mt-4 grid gap-4 border-t border-zinc-100 pt-4 text-sm sm:grid-cols-2 dark:border-zinc-800">
      {item.facts.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">Key details</h3>
          <ul className="list-disc space-y-1 pl-4 text-zinc-700 dark:text-zinc-300">
            {item.facts.map((fact) => (
              <li key={fact}>{fact}</li>
            ))}
          </ul>
        </div>
      )}
      {item.steps.length > 0 && (
        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-500">Next steps</h3>
          <ol className="list-decimal space-y-1 pl-4 text-zinc-700 dark:text-zinc-300">
            {item.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      )}

    </div>
  );
}
