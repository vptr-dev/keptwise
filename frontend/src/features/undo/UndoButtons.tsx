// The Undo and Redo buttons at the top right. Every change to saves,
// collections, tags, plans and spaces (yours or the AI's) can be undone and
// redone here; the backend keeps the steps (backend/app/db/undo.py).
// Buttons only, on purpose: no keyboard shortcuts.
import { useCallback, useEffect, useState } from "react";

import { toast } from "../../components/Toasts";
import { icons } from "../../components/icons";
import { api, errorText, onDataChange } from "../../lib/api";
import { announceChange } from "../organize/organizeApi";

type Step = { id: number; label: string } | null;
type UndoState = { undo: Step; redo: Step };

export const undoApi = {
  state: () => api.get<UndoState>("/api/undo"),
  undo: (expectedId?: number) => api.post<UndoState & { done: string }>(
    expectedId === undefined ? "/api/undo" : `/api/undo?expected_id=${expectedId}`,
  ),
  redo: () => api.post<UndoState & { done: string }>("/api/redo"),
};

const AFTER_UNDO = "kw-after-undo";

export function announceUndo(): void {
  announceChange();
  window.dispatchEvent(new Event(AFTER_UNDO));
}

/** Pages reload their data after an Undo or Redo. */
export function onUndo(listener: () => void): () => void {
  window.addEventListener(AFTER_UNDO, listener);
  return () => window.removeEventListener(AFTER_UNDO, listener);
}

const BUTTON =
  "flex h-7 w-7 items-center justify-center rounded-md p-1.5 text-zinc-600 transition hover:bg-zinc-900/5 hover:text-zinc-900 disabled:cursor-default disabled:opacity-30 disabled:hover:bg-transparent dark:text-zinc-300 dark:hover:bg-white/10 dark:hover:text-white";

export default function UndoButtons() {
  const [state, setState] = useState<UndoState>({ undo: null, redo: null });
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    undoApi.state().then(setState).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const stop = onDataChange(refresh);
    window.addEventListener("focus", refresh);
    return () => {
      stop();
      window.removeEventListener("focus", refresh);
    };
  }, [refresh]);

  async function run(which: "undo" | "redo") {
    setBusy(true);
    try {
      const result = await (which === "undo" ? undoApi.undo() : undoApi.redo());
      setState({ undo: result.undo, redo: result.redo });
      toast(`${which === "undo" ? "Undone" : "Redone"}: ${result.done}`);
      announceUndo();
    } catch (error) {
      toast(errorText(error), { tone: "error" });
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-0.5 self-center" role="group" aria-label="Undo and redo">
      <button
        type="button"
        className={BUTTON}
        disabled={!state.undo || busy}
        onClick={() => void run("undo")}
        aria-label={state.undo ? `Undo: ${state.undo.label}` : "Nothing to undo"}
        title={state.undo ? `Undo: ${state.undo.label}` : "Nothing to undo"}
      >
        {icons.undo}
      </button>
      <button
        type="button"
        className={BUTTON}
        disabled={!state.redo || busy}
        onClick={() => void run("redo")}
        aria-label={state.redo ? `Redo: ${state.redo.label}` : "Nothing to redo"}
        title={state.redo ? `Redo: ${state.redo.label}` : "Nothing to redo"}
      >
        {icons.redo}
      </button>
    </div>
  );
}
