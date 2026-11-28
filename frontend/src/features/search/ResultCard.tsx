// One saved video in search results or chat: thumbnail, title, and why it
// was found (the matching words, highlighted, and where; or the passage
// that means something similar). Click it to see everything.
import { SaveControls } from "../library/SaveControls";
import { useState, type MouseEvent } from "react";
import { useContextMenu, type MenuItem } from "../../components/ContextMenu";
import { useDialog } from "../../components/Dialog";
import { icons } from "../../components/icons";
import { Badge } from "../../components/ui";
import { formatDuration } from "../enrich/enrichApi";
import { displayTitle, type LibraryItem } from "../library/libraryApi";
import QuickActions from "../library/QuickActions";
import { saveMenuItems } from "../library/saveMenu";
import { ITEMS_DRAG } from "../organize/organizeApi";
import Highlighted from "./Highlighted";
import { whereIn, type SearchResult } from "./searchApi";

export default function ResultCard({
  item: original,
  result,
  number,
  onOpen,
  onSelect,
  selected = false,
  selecting = false,
  dragIds,
  selectionMenu,
}: {
  item: LibraryItem;
  result?: SearchResult; // search results say why they were found
  number?: number; // chat sources show their [n]
  onOpen: (id: number) => void;
  onSelect?: (id: number, range: boolean) => void;
  selected?: boolean;
  selecting?: boolean;
  dragIds?: number[];
  selectionMenu?: MenuItem[];
}) {
  const [update, setUpdate] = useState<{ base: LibraryItem; item: LibraryItem } | null>(null);
  const item = update?.base === original ? update.item : original;
  const setEdited = (next: LibraryItem) => setUpdate({ base: original, item: next });
  const [showMenu, menu] = useContextMenu();
  const [ask, dialog] = useDialog();

  function openMenu(event: MouseEvent) {
    showMenu(event, selectionMenu ?? saveMenuItems(item, { onChange: setEdited, ask }), displayTitle(item));
  }
  const meta = [item.platform_name, item.author ? `@${item.author.replace(/^@/, "")}` : null, formatDuration(item.duration_s)]
    .filter(Boolean)
    .join(" · ");

  return (
    <article
      className={`group relative flex flex-wrap items-start rounded-2xl border bg-white shadow-sm dark:bg-zinc-900 ${
        selected ? "border-indigo-500 ring-1 ring-indigo-500" : "border-zinc-200 dark:border-zinc-800"
      }`}
      onContextMenu={openMenu}
      draggable={!item.deleted}
      onDragStart={(event) => {
        event.dataTransfer.setData(ITEMS_DRAG, JSON.stringify({ itemId: item.id, fromId: null, itemIds: dragIds }));
        event.dataTransfer.effectAllowed = "copyMove";
      }}
    >
      {onSelect && (
        <button type="button" role="checkbox" aria-checked={selected} aria-label={`Select ${displayTitle(item)}`}
          className={`ml-3 mt-4 h-6 w-6 rounded-md border-2 p-0.5 group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100
            ${selected ? "border-indigo-600 bg-indigo-600 text-white" : "border-zinc-400"} ${selecting ? "" : "opacity-0"}`}
          onClick={(event) => onSelect(item.id, event.shiftKey)}>{selected && icons.check}</button>
      )}
      <button
        type="button"
        onClick={(event) => {
          if (onSelect && (selecting || event.ctrlKey || event.shiftKey)) onSelect(item.id, event.shiftKey);
          else onOpen(item.id);
        }}
        className="flex min-w-52 flex-1 gap-3 rounded-2xl p-3 text-left hover:text-indigo-700 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:hover:text-indigo-300"
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
        <p className="mt-1 truncate font-medium">{displayTitle(item)}</p>
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
      {!selecting && !item.deleted && (
        <div className="flex items-center gap-2 p-3">
          <SaveControls id={item.id} title={displayTitle(item)} select={!onSelect} onChange={setEdited} />
          <QuickActions item={item} onChange={setEdited} visible inline />
          <button type="button" aria-label={`Actions for ${displayTitle(item)}`} title="More actions"
            className="h-7 w-7 rounded p-1 text-zinc-600 hover:bg-zinc-200 focus-visible:outline-2 dark:text-zinc-300 dark:hover:bg-zinc-700"
            onClick={openMenu}>{icons.more}</button>
        </div>
      )}
      {menu}
      {dialog}
    </article>
  );
}
