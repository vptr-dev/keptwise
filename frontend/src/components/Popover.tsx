// A small floating panel next to a button, drawn on top of everything (so
// cards with hidden overflow don't cut it off). Closes on Esc or a click
// outside.
import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export default function Popover({
  anchor,
  onClose,
  children,
  width = 260,
  label,
}: {
  anchor: HTMLElement | null;
  onClose: () => void;
  children: ReactNode;
  width?: number;
  label: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!anchor) return;
    const rect = anchor.getBoundingClientRect();
    const height = box.current?.offsetHeight ?? 300;
    let top = rect.bottom + 6;
    if (top + height > window.innerHeight - 8) top = Math.max(8, rect.top - height - 6);
    const left = Math.min(Math.max(8, rect.right - width), window.innerWidth - width - 8);
    setPlace({ top, left });
  }, [anchor, width]);

  useEffect(() => {
    const away = (event: MouseEvent) => {
      const target = event.target as Node;
      if (box.current?.contains(target) || anchor?.contains(target)) return;
      onClose();
    };
    const esc = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
      }
    };
    document.addEventListener("mousedown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [anchor, onClose]);

  return createPortal(
    <div
      ref={box}
      role="dialog"
      aria-label={label}
      style={{ top: place?.top ?? -9999, left: place?.left ?? -9999, width }}
      className="kw-fade kw-glass-pop fixed z-50 rounded-xl border border-zinc-200 bg-white p-2 text-sm shadow-xl dark:border-zinc-700 dark:bg-zinc-900"
      onClick={(event) => event.stopPropagation()}
    >
      {children}
    </div>,
    document.body,
  );
}
