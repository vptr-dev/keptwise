import { useEffect, useState } from "react";

type Frame = { integrated: boolean; maximized: boolean; fullscreen: boolean };
type Desktop = { info?: () => Promise<Frame>; caption?: (action: string) => Promise<void> };
const desktop = () => (window as Window & { pywebview?: { api: Desktop } }).pywebview?.api;

export default function CaptionBar() {
  const [frame, setFrame] = useState<Frame | null>(null);
  useEffect(() => {
    let mounted = true;
    const refresh = () => desktop()?.info?.().then((value) => { if (mounted) setFrame(value); }).catch(() => undefined);
    refresh();
    const events = ["pywebviewready", "keptwise-frame", "resize"];
    events.forEach((event) => window.addEventListener(event, refresh));
    return () => {
      mounted = false;
      events.forEach((event) => window.removeEventListener(event, refresh));
    };
  }, []);

  if (!frame?.integrated || frame.fullscreen) return null;
  const command = (action: string) => void desktop()?.caption?.(action).catch(() => undefined);
  const buttons = [
    { action: "minimize", label: "Minimise", shape: "M3 7h8" },
    { action: "maximize", label: frame.maximized ? "Restore" : "Maximise",
      shape: frame.maximized ? "M5 3h6v6M3 5h6v6H3z" : "M3 3h8v8H3z" },
    { action: "close", label: "Close window", shape: "m3 3 8 8m0-8-8 8" },
  ];

  return (
    <div className="flex w-full min-w-0 select-none items-stretch" aria-label="Window controls">
      <div className="flex flex-1 items-center px-4 text-xs font-medium text-zinc-500 dark:text-zinc-300"
        onPointerDown={(event) => { if (event.button === 0 && event.detail <= 1) command("move"); }}
        onDoubleClick={() => command("maximize")}>
        Keptwise
      </div>
      {buttons.map(({ action, label, shape }) => (
        <button type="button" key={action} aria-label={label} title={label}
          className={"grid h-9 w-11 place-items-center outline-offset-[-2px] focus-visible:outline-2 " +
            (action === "close" ? "hover:bg-red-600 hover:text-white" : "hover:bg-zinc-500/15")}
          onClick={() => command(action)}>
          <svg viewBox="0 0 14 14" width="14" height="14" fill="none" stroke="currentColor" aria-hidden="true">
            <path d={shape} />
          </svg>
        </button>
      ))}
    </div>
  );
}
