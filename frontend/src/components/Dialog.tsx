// Small "are you sure?", "type a name" and "pick one" boxes, used by the
// right-click menus. `const [ask, dialog] = useDialog()`, render `{dialog}`,
// then `await ask.text(...)`, `await ask.confirm(...)` or `await ask.pick(...)`.
// Each answers null / false when cancelled.
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { Button, inputClass } from "./ui";

type Choice = { value: string; label: string };
type Request =
  | { kind: "text"; title: string; label: string; value: string; confirm: string; maxLength: number; hint?: ReactNode; done: (answer: string | null) => void }
  | { kind: "confirm"; title: string; body: ReactNode; confirm: string; danger: boolean; done: (answer: boolean) => void }
  | { kind: "pick"; title: string; label: string; options: Choice[]; confirm: string; hint?: ReactNode; done: (answer: string | null) => void };

export type Ask = {
  text: (o: { title: string; label: string; value?: string; confirm?: string; maxLength?: number; hint?: ReactNode }) => Promise<string | null>;
  confirm: (o: { title: string; body: ReactNode; confirm?: string; danger?: boolean }) => Promise<boolean>;
  pick: (o: { title: string; label: string; options: Choice[]; confirm?: string; hint?: ReactNode }) => Promise<string | null>;
};

export function useDialog(): [Ask, ReactNode] {
  const [request, setRequest] = useState<Request | null>(null);
  const ask = useMemo<Ask>(
    () => ({
      text: (o) =>
        new Promise((resolve) =>
          setRequest({ kind: "text", value: "", confirm: "Save", maxLength: 80, ...o, done: resolve }),
        ),
      confirm: (o) =>
        new Promise((resolve) => setRequest({ kind: "confirm", confirm: "OK", danger: false, ...o, done: resolve })),
      pick: (o) => new Promise((resolve) => setRequest({ kind: "pick", confirm: "OK", ...o, done: resolve })),
    }),
    [],
  );
  const finish = useCallback(
    (answer: string | boolean | null) => {
      if (!request) return;
      setRequest(null);
      (request.done as (a: string | boolean | null) => void)(answer);
    },
    [request],
  );
  return [ask, request ? <DialogBox request={request} onFinish={finish} /> : null];
}

function DialogBox({ request, onFinish }: { request: Request; onFinish: (answer: string | boolean | null) => void }) {
  const [text, setText] = useState(request.kind === "text" ? request.value : request.kind === "pick" ? request.options[0]?.value ?? "" : "");
  const first = useRef<HTMLInputElement & HTMLSelectElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const cancel = () => onFinish(request.kind === "confirm" ? false : null);

  const cancelNow = useRef(cancel);
  cancelNow.current = cancel;

  // Focus (and select the old name) once, when the box opens. Doing it on
  // every render selected the text after each key, so the next key wiped it.
  useEffect(() => {
    if (first.current) {
      first.current.focus();
      if (request.kind === "text") first.current.select?.();
    } else form.current?.querySelector<HTMLButtonElement>("button[type=submit]")?.focus();
  }, [request]);

  useEffect(() => {
    const esc = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        cancelNow.current();
      }
    };
    document.addEventListener("keydown", esc, true);
    return () => document.removeEventListener("keydown", esc, true);
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (request.kind === "confirm") return onFinish(true);
    if (!text.trim()) return;
    onFinish(text.trim());
  }

  return createPortal(
    <div
      className="kw-fade fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-4"
      onMouseDown={(e) => {
        e.stopPropagation();
        if (e.target === e.currentTarget) cancel();
      }}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => e.stopPropagation()}
    >
      <form
        role="dialog"
        aria-modal="true"
        aria-label={request.title}
        ref={form}
        onSubmit={submit}
        className="kw-rise kw-glass-pop w-full max-w-sm space-y-4 rounded-2xl border border-zinc-200 bg-white p-5 shadow-2xl dark:border-zinc-700 dark:bg-zinc-900"
      >
        <h2 className="text-base font-semibold">{request.title}</h2>
        {request.kind === "confirm" && <div className="text-sm text-zinc-600 dark:text-zinc-400">{request.body}</div>}
        {request.kind === "text" && (
          <label className="block space-y-1.5">
            <span className="text-sm text-zinc-600 dark:text-zinc-400">{request.label}</span>
            <input ref={first} className={inputClass} aria-label={request.label} maxLength={request.maxLength} value={text} onChange={(e) => setText(e.target.value)} />
            {request.hint && <span className="block text-xs text-zinc-500">{request.hint}</span>}
          </label>
        )}
        {request.kind === "pick" && (
          <label className="block space-y-1.5">
            <span className="text-sm text-zinc-600 dark:text-zinc-400">{request.label}</span>
            <select ref={first} className={inputClass} aria-label={request.label} value={text} onChange={(e) => setText(e.target.value)}>
              {request.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            {request.hint && <span className="block text-xs text-zinc-500">{request.hint}</span>}
          </label>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={cancel}>
            Cancel
          </Button>
          <Button type="submit" variant={request.kind === "confirm" && request.danger ? "danger" : "primary"} disabled={request.kind !== "confirm" && !text.trim()}>
            {request.confirm}
          </Button>
        </div>
      </form>
    </div>,
    document.body,
  );
}
