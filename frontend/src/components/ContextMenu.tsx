// The right-click menu for saves, collections and tags. A component calls
// `const [openMenu, menu] = useContextMenu()`, renders `{menu}` anywhere, and
// passes `(event) => openMenu(event, items)` as onContextMenu. The keyboard's
// menu key (or Shift+F10) opens it too. An item can open a small panel in
// place of the menu (e.g. the tags pop-up), so the panels on the hover
// buttons work from here as well.
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import ColourPicker, { Swatch, colourLabel } from "./ColourPicker";
import { icons } from "./icons";

export type MenuItem =
  | {
      kind?: "item";
      label: string;
      icon?: ReactNode;
      onSelect: () => void;
      danger?: boolean;
      disabled?: boolean;
      checked?: boolean; // shows a tick (for on/off choices)
      hint?: string; // greyed text on the right, e.g. a shortcut
    }
  | { kind: "panel"; label: string; icon?: ReactNode; title: string; width?: number; panel: (close: () => void) => ReactNode }
  | { kind: "colors"; label: string; value: string | null; onPick: (color: string | null) => void } // null: the accent colour
  | { kind: "divider" }
  | { kind: "heading"; label: string };

type Open = { x: number; y: number; title?: string; items: MenuItem[]; panel?: { title: string; width: number; render: (close: () => void) => ReactNode } };

const ROW =
  "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-sm outline-none disabled:cursor-default disabled:opacity-40";

/** A right-click menu. Returns the function that opens it and the element to render. */
export function useContextMenu(): [(event: ReactMouseEvent, items: MenuItem[], title?: string) => void, ReactNode] {
  const [open, setOpen] = useState<Open | null>(null);
  const close = useCallback(() => setOpen(null), []);
  const show = useCallback((event: ReactMouseEvent, items: MenuItem[], title?: string) => {
    event.preventDefault();
    event.stopPropagation();
    // From the keyboard there's no mouse spot: use the element's corner.
    let { clientX: x, clientY: y } = event;
    if (x === 0 && y === 0) {
      const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
      x = rect.left + 12;
      y = rect.top + 12;
    }
    setOpen({ x, y, title, items });
  }, []);
  const element = open ? <MenuBox open={open} onClose={close} onPanel={(panel) => setOpen({ ...open, panel })} /> : null;
  return [show, element];
}

function MenuBox({ open, onClose, onPanel }: { open: Open; onClose: () => void; onPanel: (panel: NonNullable<Open["panel"]>) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ top: number; left: number } | null>(null);
  const width = Math.min(open.panel?.width ?? 280, window.innerWidth - 16);

  useLayoutEffect(() => {
    const height = box.current?.offsetHeight ?? 300;
    const top = Math.max(8, Math.min(open.y, window.innerHeight - height - 8));
    const left = Math.max(8, Math.min(open.x, window.innerWidth - width - 8));
    setPlace({ top, left });
  }, [open.x, open.y, open.panel, width]);

  // Focus the first choice so the arrow keys work straight away.
  useEffect(() => {
    if (open.panel) return;
    box.current?.querySelector<HTMLElement>("[role=menuitem]:not([disabled]),[role=menuitemcheckbox]:not([disabled])")?.focus();
  }, [open.panel]);

  useEffect(() => {
    const away = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) onClose();
    };
    const keys = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (open.panel || !box.current) return;
      const choices = [...box.current.querySelectorAll<HTMLElement>("[role^=menuitem]:not([disabled])")];
      const at = choices.indexOf(document.activeElement as HTMLElement);
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        const next = event.key === "ArrowDown" ? (at + 1) % choices.length : (at - 1 + choices.length) % choices.length;
        choices[next]?.focus();
      }
    };
    const gone = () => onClose();
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", keys, true);
    window.addEventListener("blur", gone);
    window.addEventListener("resize", gone);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", keys, true);
      window.removeEventListener("blur", gone);
      window.removeEventListener("resize", gone);
    };
  }, [onClose, open.panel]);

  const keep = (event: { stopPropagation: () => void }) => event.stopPropagation();

  return createPortal(
    <div
      ref={box}
      role={open.panel ? "dialog" : "menu"}
      aria-label={open.panel?.title ?? open.title ?? "Actions"}
      style={{ top: place?.top ?? -9999, left: place?.left ?? -9999, width }}
      className="kw-fade kw-glass-pop fixed z-[60] max-h-[calc(100vh-16px)] overflow-y-auto rounded-xl border border-zinc-200 bg-white p-1.5 text-zinc-800 shadow-xl dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
      // Keep clicks inside from reaching the card or link underneath.
      onClick={keep}
      onMouseDown={keep}
      onContextMenu={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      {open.panel ? (
        open.panel.render(onClose)
      ) : (
        <>
          {open.title && <p className="truncate px-2.5 pb-1 pt-1 text-xs font-semibold text-zinc-500">{open.title}</p>}
          {open.items.map((item, index) => (
            <Row key={index} item={item} onClose={onClose} onPanel={onPanel} />
          ))}
        </>
      )}
    </div>,
    document.body,
  );
}

function Row({ item, onClose, onPanel }: { item: MenuItem; onClose: () => void; onPanel: (panel: NonNullable<Open["panel"]>) => void }) {
  if (item.kind === "divider") return <div role="separator" className="my-1 border-t border-zinc-100 dark:border-zinc-800" />;
  if (item.kind === "heading")
    return <p className="px-2.5 pb-0.5 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">{item.label}</p>;
  if (item.kind === "colors")
    return (
      <button
        type="button"
        role="menuitem"
        className={`${ROW} hover:bg-zinc-100 focus:bg-zinc-100 dark:hover:bg-zinc-800 dark:focus:bg-zinc-800`}
        onClick={() =>
          onPanel({
            title: item.label,
            width: 232,
            render: (close) => (
              <ColourPicker
                value={item.value}
                onPick={(colour) => {
                  item.onPick(colour);
                  close();
                }}
              />
            ),
          })
        }
      >
        <span className="flex h-4 w-4 shrink-0 items-center justify-center text-zinc-500">{icons.palette}</span>
        <span className="flex-1 truncate">{item.label}…</span>
        <span className="flex items-center gap-1.5 text-xs text-zinc-400">
          <Swatch colour={item.value === "accent" ? null : item.value} />
          {colourLabel(item.value)}
        </span>
      </button>
    );
  if (item.kind === "panel")
    return (
      <button
        type="button"
        role="menuitem"
        className={`${ROW} hover:bg-zinc-100 focus:bg-zinc-100 dark:hover:bg-zinc-800 dark:focus:bg-zinc-800`}
        onClick={() => onPanel({ title: item.title, width: item.width ?? 260, render: item.panel })}
      >
        <span className="h-4 w-4 shrink-0 text-zinc-500">{item.icon}</span>
        <span className="flex-1 truncate">{item.label}</span>
        <span className="h-3.5 w-3.5 shrink-0 -rotate-90 text-zinc-400">{icons.down}</span>
      </button>
    );
  const checkable = item.checked !== undefined;
  return (
    <button
      type="button"
      role={checkable ? "menuitemcheckbox" : "menuitem"}
      aria-checked={checkable ? item.checked : undefined}
      disabled={item.disabled}
      className={`${ROW} ${
        item.danger
          ? "text-red-600 hover:bg-red-50 focus:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40 dark:focus:bg-red-950/40"
          : "hover:bg-zinc-100 focus:bg-zinc-100 dark:hover:bg-zinc-800 dark:focus:bg-zinc-800"
      }`}
      onClick={() => {
        onClose();
        item.onSelect();
      }}
    >
      <span className={`h-4 w-4 shrink-0 ${item.danger ? "" : "text-zinc-500"}`}>{checkable ? (item.checked ? icons.check : null) : item.icon}</span>
      <span className="min-w-0 flex-1">{item.label}</span>
      {item.hint && <span className="max-w-[40%] shrink-0 text-right text-xs text-zinc-500">{item.hint}</span>}
    </button>
  );
}
