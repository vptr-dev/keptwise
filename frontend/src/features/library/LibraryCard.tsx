// One save in the Library grid: picture, title, type, tags and progress.
// The whole card is a link to the item page, so Tab and Enter work.
// With the mouse over it, quick buttons tag it, file it, add it to a plan
// or unsave it. Right-click (or the menu key) shows every action. While
// selecting, a click ticks it instead (Shift-click ticks a whole run).
import { SaveControls } from "./SaveControls";
import { useState, type DragEvent, type MouseEvent } from "react";

import { useContextMenu, type MenuItem } from "../../components/ContextMenu";
import { useDialog } from "../../components/Dialog";
import { icons } from "../../components/icons";
import { ITEMS_DRAG, type ItemsDrag } from "../organize/organizeApi";
import { displayTitle, formatDate, stepProgress, type LibraryItem } from "./libraryApi";
import QuickActions from "./QuickActions";
import { saveMenuItems } from "./saveMenu";
import Thumb from "./Thumb";

function statusLine(item: LibraryItem): string | null {
  if (item.gone) return "Unavailable";
  if (item.status === "failed") return "Couldn't read this one";
  if (item.status === "imported") return "Not transcribed yet";
  if (item.status === "enriched") return "Needs notes";
  return item.kind_label;
}

const MAX_TAGS_SHOWN = 3;

export default function LibraryCard({
  item,
  selecting = false,
  selected = false,
  onSelect,
  dragIds,
  fromId = null,
  onChange,
  actions = true,
  from = null,
  menuExtra,
  menuItems,
}: {
  item: LibraryItem;
  selecting?: boolean;
  selected?: boolean;
  onSelect?: (event: MouseEvent) => void;
  dragIds?: number[]; // dragging this card carries these saves (the selection)
  fromId?: number | null; // the collection the grid is showing, if any
  onChange?: (item: LibraryItem) => void; // after a quick action changed it
  actions?: boolean; // show the quick buttons on hover
  from?: { id: number; name: string } | null; // the collection shown, for "Take out of"
  menuExtra?: MenuItem[]; // right-click choices only this screen has
  menuItems?: MenuItem[]; // the whole menu, instead of the usual one (a selection, the Archive)
}) {
  const [hover, setHover] = useState(false);
  const [openMenu, menu] = useContextMenu();
  const [ask, dialog] = useDialog();
  const { done, total } = stepProgress(item);
  const started = done > 0 && !item.done;
  const line = statusLine(item);

  function startDrag(event: DragEvent) {
    const drag: ItemsDrag = { itemId: item.id, fromId, itemIds: dragIds };
    event.dataTransfer.setData(ITEMS_DRAG, JSON.stringify(drag));
    event.dataTransfer.effectAllowed = "copyMove";
  }

  return (
    <a
      href={`#/item/${item.id}`}
      data-testid={`library-${item.id}`}
      draggable
      onDragStart={startDrag}
      onClick={(event) => {
        if (selecting || event.ctrlKey || event.shiftKey) {
          event.preventDefault();
          onSelect?.(event);
        }
      }}
      aria-pressed={selecting ? selected : undefined}
      onContextMenu={(event) => {
        if (menuItems) openMenu(event, menuItems);
        else if (onChange) openMenu(event, saveMenuItems(item, { onChange, ask, from, extra: menuExtra }), displayTitle(item));
      }}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className={`group relative flex w-full flex-col overflow-hidden rounded-2xl border bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:bg-zinc-900 dark:hover:border-zinc-700 ${
        selected ? "border-indigo-500 ring-2 ring-indigo-500" : "border-zinc-200 dark:border-zinc-800"
      }`}
    >
      <div className="relative">
        <Thumb item={item} className="aspect-[4/5] w-full" />
        {onSelect && (
          <button
            type="button"
            role="checkbox"
            aria-checked={selected}
            aria-label={`Select ${displayTitle(item)}`}
            title="Select (Ctrl+click also works; Shift+click selects a run)"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onSelect(event);
            }}
            className={`absolute left-2 top-2 flex h-8 w-8 items-center justify-center rounded-md border-2 p-0.5 shadow transition ${
              selected
                ? "border-indigo-600 bg-indigo-600 text-white"
                : `border-white bg-black/50 text-white hover:bg-black/50 hover:text-white ${
                    selecting || hover ? "opacity-100" : "opacity-0 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100"
                  }`
            }`}
          >
            {selected ? icons.check : icons.select}
          </button>
        )}
        {!selecting && (onChange || item.gone || item.deleted) && <span className="absolute bottom-2 right-2">
          <SaveControls id={item.id} title={displayTitle(item)} archived={item.deleted} select={false} onChange={onChange} />
        </span>}
        {item.done && (
          <span
            title="Done"
            className="absolute bottom-2 left-2 flex h-6 w-6 items-center justify-center rounded-full bg-emerald-500 p-1 text-white shadow"
          >
            {icons.check}
          </span>
        )}
        {actions && !selecting && onChange && <QuickActions item={item} onChange={onChange} visible={hover} />}
        {menu}
        {dialog}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        <h3 className="line-clamp-2 text-sm font-medium leading-snug text-zinc-900 group-hover:text-indigo-700 dark:text-zinc-100 dark:group-hover:text-indigo-300">
          {displayTitle(item)}
        </h3>
        {item.collections.length > 0 && (
          <p className="truncate text-[11px] font-medium text-indigo-600 dark:text-indigo-400" title={item.collections.map((c) => c.name).join(", ")}>
            {item.collections.map((c) => c.name).join(" · ")}
          </p>
        )}
        {item.tags.length > 0 && (
          <p className="truncate text-[11px] text-zinc-500 dark:text-zinc-400" title={item.tags.map((t) => `#${t}`).join(" ")}>
            {item.tags.slice(0, MAX_TAGS_SHOWN).map((t) => `#${t}`).join(" ")}
            {item.tags.length > MAX_TAGS_SHOWN ? ` +${item.tags.length - MAX_TAGS_SHOWN}` : ""}
          </p>
        )}
        <p className="mt-auto truncate text-xs text-zinc-500 dark:text-zinc-400">
          {[line, formatDate(item.saved_at)].filter(Boolean).join(" · ")}
        </p>
        {started && total > 0 && (
          <div className="mt-1 flex items-center gap-2" title={`${done} of ${total} steps done`}>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
              <div className="h-full rounded-full bg-indigo-500" style={{ width: `${(done / total) * 100}%` }} />
            </div>
            <span className="text-[11px] tabular-nums text-zinc-500">
              {done}/{total}
            </span>
          </div>
        )}
      </div>
    </a>
  );
}
