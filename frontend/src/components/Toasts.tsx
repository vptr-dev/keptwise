// Short messages in the bottom corner after a quick change ("Added to Food"),
// often with an Undo button. `toast("Added to Food", { undo: () => ... })`
// works from anywhere; <Toasts /> (in the app frame) shows them.
import { useEffect, useState } from "react";

import { icons } from "./icons";

type Toast = { id: number; text: string; undo?: () => void | Promise<unknown>; tone: "info" | "error" };

let next = 1;
let current: Toast[] = [];
const listeners = new Set<(toasts: Toast[]) => void>();

function publish(list: Toast[]) {
  current = list;
  listeners.forEach((listener) => listener(current));
}

export function dismissToast(id: number): void {
  publish(current.filter((t) => t.id !== id));
}

export function toast(text: string, options: { undo?: () => void | Promise<unknown>; tone?: "info" | "error" } = {}): number {
  const id = next++;
  publish([...current.slice(-2), { id, text, undo: options.undo, tone: options.tone ?? "info" }]);
  window.setTimeout(() => dismissToast(id), options.undo ? 7000 : 4000);
  return id;
}

export default function Toasts() {
  const [list, setList] = useState<Toast[]>(current);
  useEffect(() => {
    listeners.add(setList);
    return () => {
      listeners.delete(setList);
    };
  }, []);
  if (list.length === 0) return null;
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-80 flex-col gap-2" aria-live="polite">
      {list.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`pointer-events-auto flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm shadow-lg ${
            t.tone === "error" ? "bg-red-600 text-white" : "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
          }`}
        >
          <span className="flex-1">{t.text}</span>
          {t.undo && (
            <button
              type="button"
              className="font-semibold text-indigo-300 hover:underline dark:text-indigo-700"
              onClick={() => {
                dismissToast(t.id);
                void Promise.resolve(t.undo?.()).catch(() => toast("Couldn't undo that.", { tone: "error" }));
              }}
            >
              Undo
            </button>
          )}
          <button type="button" aria-label="Close" className="h-4 w-4 opacity-60 hover:opacity-100" onClick={() => dismissToast(t.id)}>
            {icons.close}
          </button>
        </div>
      ))}
    </div>
  );
}
