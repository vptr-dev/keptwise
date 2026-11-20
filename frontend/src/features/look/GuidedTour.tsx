import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

import { icons } from "../../components/icons";
import Logo from "../../components/Logo";
import { Badge, Button, inputClass } from "../../components/ui";
import { CHAPTERS } from "./tourChapters";

const PRACTICE_SAVES = [
  { title: "Lemon pasta", text: "Save a cup of pasta water for the sauce." },
  { title: "Weekend in Edinburgh", text: "Start at the castle, then walk to the gardens." },
];

export default function GuidedTour({ onClose }: { onClose: (destination?: string) => void }) {
  const [index, setIndex] = useState(0);
  const [imported, setImported] = useState(false);
  const [phase, setPhase] = useState(0);
  const [folder, setFolder] = useState("Recipes");
  const [query, setQuery] = useState("");
  const titleRef = useRef<HTMLHeadingElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const chapter = CHAPTERS[index];
  const last = index === CHAPTERS.length - 1;
  const matches = PRACTICE_SAVES.filter((save) =>
    (save.title + " " + save.text).toLowerCase().includes(query.trim().toLowerCase()));

  useEffect(() => {
    const before = document.activeElement;
    return () => {
      if (before instanceof HTMLElement && before.isConnected) before.focus();
    };
  }, []);

  useEffect(() => {
    contentRef.current?.scrollTo?.({ top: 0 });
    titleRef.current?.focus({ preventScroll: true });
  }, [index]);

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;
    const targets = Array.from(event.currentTarget.querySelectorAll<HTMLElement>("button:not([disabled]), input, select"));
    const first = targets[0];
    const final = targets.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === titleRef.current)) {
      event.preventDefault();
      final?.focus();
    } else if (!event.shiftKey && document.activeElement === final) {
      event.preventDefault();
      first?.focus();
    }
  }

  return createPortal(
    <div className="kw-fade fixed inset-0 z-[85] grid place-items-center bg-zinc-950/60 p-3 backdrop-blur-sm sm:p-6">
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-name"
        onKeyDown={onKeyDown}
        className="kw-rise flex max-h-full w-full max-w-2xl flex-col overflow-hidden rounded-3xl bg-white shadow-2xl dark:bg-zinc-900"
      >
        <header className="flex shrink-0 items-center gap-3 px-5 pt-5 sm:px-7">
          <Logo className="h-8 w-8 shrink-0" />
          <h2 id="tour-name" className="flex-1 font-semibold">Keptwise tutorial</h2>
          <Button variant="ghost" size="sm" onClick={() => onClose()}>Close tutorial</Button>
        </header>
        <div role="progressbar" aria-label="Tutorial progress" aria-valuemin={0} aria-valuemax={CHAPTERS.length}
          aria-valuenow={index + 1} className="mx-5 mt-4 flex gap-1 sm:mx-7">
          {CHAPTERS.map(({ id }, n) => (
            <span key={id} className={"h-1 flex-1 rounded-full " + (n <= index ? "bg-indigo-600" : "bg-zinc-200 dark:bg-zinc-700")} />
          ))}
        </div>
        <div ref={contentRef} className="min-h-0 overflow-y-auto px-5 py-5 sm:px-7">
          <h3 ref={titleRef} tabIndex={-1} className="text-2xl font-semibold tracking-tight outline-none">{chapter.title}</h3>
          <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{chapter.intro}</p>

          <div className="mt-5 space-y-3 rounded-2xl bg-indigo-50 p-4 dark:bg-indigo-950/40">
            {chapter.id === "import" && (
              <>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="h-5 w-5 text-indigo-600 dark:text-indigo-300">{icons.import}</span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">Sample export.zip</span>
                  <Button size="sm" variant="secondary" disabled={imported} onClick={() => setImported(true)}>Try sample import</Button>
                </div>
                {imported && <p role="status" className="text-sm">Two sample saves added. Next, sort one of them.</p>}
              </>
            )}
            {chapter.id === "sort" && (
              <>
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-medium">Lemon pasta</span>
                  <Badge tone={phase === 3 ? "green" : "indigo"}>
                    {["Waiting", "Transcript ready", "Ready to review", "Filed"][phase]}
                  </Badge>
                </div>
                {phase >= 1 && <p className="text-sm"><b>Transcript</b> “Save a cup of pasta water for the sauce.”</p>}
                {phase >= 2 && <p className="text-sm"><b>Note</b> Keep a cup of pasta water before draining.</p>}
                {phase < 2 && <Button size="sm" onClick={() => setPhase(phase + 1)}>
                  {phase === 0 ? "Get transcript" : "Write notes"}
                </Button>}
                {phase === 2 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="flex items-center gap-2 text-sm">
                      Suggested collection
                      <select value={folder} onChange={(event) => setFolder(event.target.value)}
                        className="rounded-lg border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-600 dark:bg-zinc-900">
                        <option>Recipes</option>
                        <option>Weeknight meals</option>
                      </select>
                    </label>
                    <Button size="sm" onClick={() => setPhase(3)}>Approve</Button>
                  </div>
                )}
                {phase === 3 && <p role="status" className="text-sm">Filed in {folder}.</p>}
              </>
            )}
            {chapter.id === "search" && (
              <>
                <input type="search" className={inputClass} value={query} onChange={(event) => setQuery(event.target.value)}
                  aria-label="Search practice saves" placeholder="Try “pasta water”" />
                <ul aria-live="polite" className="space-y-2">
                  {matches.map((save) => (
                    <li key={save.title} className="rounded-xl bg-white px-3 py-2 text-sm dark:bg-zinc-900">
                      <p className="font-medium">{save.title}</p>
                      <p className="text-zinc-600 dark:text-zinc-400">{save.text}</p>
                    </li>
                  ))}
                  {matches.length === 0 && <li className="text-sm">No sample saves matched.</li>}
                </ul>
              </>
            )}
          </div>
        </div>
        <footer className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-zinc-200 px-5 py-4 sm:px-7 dark:border-zinc-800">
          <Button variant="ghost" disabled={index === 0} onClick={() => setIndex(index - 1)}>Back</Button>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" onClick={() => onClose(chapter.destination[1])}>{chapter.destination[0]}</Button>
            <Button onClick={() => last ? onClose() : setIndex(index + 1)}>{last ? "Finish tutorial" : "Next chapter"}</Button>
          </div>
        </footer>
      </section>
    </div>,
    document.body,
  );
}
