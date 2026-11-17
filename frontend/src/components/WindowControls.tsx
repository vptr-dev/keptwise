// The app's own minimise / maximise / close buttons and resize edges.
// The window has no Windows title bar (desktop/launcher.py makes it
// "frameless"), so these talk to Python through window.pywebview.api.
// In a normal browser (developer mode) there is no pywebview, so nothing shows.
import { useEffect, useRef, useState } from "react";

type DesktopApi = {
  minimize: () => Promise<void>;
  toggle_maximize: () => Promise<boolean>;
  is_maximized: () => Promise<boolean>;
  close: () => Promise<void>;
  size: () => Promise<[number, number]>;
  resize: (width: number, height: number) => Promise<void>;
  set_accent?: (accent: string, dark: boolean) => Promise<boolean>; // tints the taskbar icon
};

declare global {
  interface Window {
    pywebview?: { api: DesktopApi };
  }
}

/** The desktop window's controls, or null when running in a browser. */
export function useDesktopWindow(): DesktopApi | null {
  const [desktop, setDesktop] = useState<DesktopApi | null>(() => window.pywebview?.api ?? null);
  useEffect(() => {
    if (desktop) return;
    const ready = () => setDesktop(window.pywebview?.api ?? null);
    window.addEventListener("pywebviewready", ready);
    return () => window.removeEventListener("pywebviewready", ready);
  }, [desktop]);
  return desktop;
}

// The icon itself changes colour under the mouse (grey to the text colour,
// and to red for Close); there is no box behind it.
const BUTTON =
  "group flex h-full w-10 items-center justify-center text-zinc-400 transition-colors focus-visible:outline-2 focus-visible:-outline-offset-4 focus-visible:outline-indigo-500 dark:text-zinc-500";
const CALM = `${BUTTON} hover:text-zinc-900 dark:hover:text-white`;
const CLOSE = `${BUTTON} hover:text-red-500 active:text-red-600`;
const ICON = "h-3.5 w-3.5 transition-transform duration-150 group-hover:scale-125 group-active:scale-100";
const STROKE = { fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round", strokeLinejoin: "round" } as const;

export function WindowButtons({ desktop }: { desktop: DesktopApi }) {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    desktop.is_maximized().then(setMaximized).catch(() => undefined);
  }, [desktop]);

  const toggle = () => desktop.toggle_maximize().then(setMaximized).catch(() => undefined);

  return (
    <div className="flex shrink-0 items-stretch pr-1.5" role="group" aria-label="Window">
      <button type="button" className={CALM} onClick={() => void desktop.minimize()} title="Minimise" aria-label="Minimise">
        <svg viewBox="0 0 14 14" className={ICON} {...STROKE} aria-hidden="true">
          <path d="M3 9.5h8" />
        </svg>
      </button>
      <button
        type="button"
        className={CALM}
        onClick={() => void toggle()}
        title={maximized ? "Restore" : "Maximise"}
        aria-label={maximized ? "Restore" : "Maximise"}
      >
        {maximized ? (
          <svg viewBox="0 0 14 14" className={ICON} {...STROKE} aria-hidden="true">
            <rect x="2.5" y="4.5" width="7" height="7" rx="1.8" />
            <path d="M5 2.5h4.7a1.8 1.8 0 0 1 1.8 1.8V9" />
          </svg>
        ) : (
          <svg viewBox="0 0 14 14" className={ICON} {...STROKE} aria-hidden="true">
            <rect x="2.5" y="2.5" width="9" height="9" rx="2.4" />
          </svg>
        )}
      </button>
      <button type="button" className={CLOSE} onClick={() => void desktop.close()} title="Close" aria-label="Close">
        <svg viewBox="0 0 14 14" className={ICON} {...STROKE} aria-hidden="true">
          <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" />
        </svg>
      </button>
    </div>
  );
}

/** Double-clicking the top bar maximises, like a normal Windows title bar. */
export function toggleMaximizeOnDoubleClick(desktop: DesktopApi | null) {
  return (event: React.MouseEvent) => {
    if (desktop && event.target === event.currentTarget) void desktop.toggle_maximize();
  };
}

type Edge = "right" | "bottom" | "corner";

/** Thin invisible strips on the right and bottom edges that resize the window. */
export function ResizeEdges({ desktop }: { desktop: DesktopApi }) {
  const drag = useRef<{ edge: Edge; x: number; y: number; w: number; h: number } | null>(null);
  const frame = useRef(0);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      const d = drag.current;
      if (!d) return;
      const width = d.edge === "bottom" ? d.w : d.w + event.screenX - d.x;
      const height = d.edge === "right" ? d.h : d.h + event.screenY - d.y;
      cancelAnimationFrame(frame.current);
      frame.current = requestAnimationFrame(() => void desktop.resize(width, height));
    };
    const up = () => {
      drag.current = null;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [desktop]);

  const start = (edge: Edge) => (event: React.PointerEvent) => {
    event.preventDefault();
    const { screenX: x, screenY: y } = event;
    desktop
      .size()
      .then(([w, h]) => {
        drag.current = { edge, x, y, w, h };
      })
      .catch(() => undefined);
  };

  return (
    <>
      <div aria-hidden="true" onPointerDown={start("right")} className="fixed inset-y-0 right-0 z-50 w-1.5 cursor-ew-resize" />
      <div aria-hidden="true" onPointerDown={start("bottom")} className="fixed inset-x-0 bottom-0 z-50 h-1.5 cursor-ns-resize" />
      <div aria-hidden="true" onPointerDown={start("corner")} className="fixed bottom-0 right-0 z-50 h-3 w-3 cursor-nwse-resize" />
    </>
  );
}
