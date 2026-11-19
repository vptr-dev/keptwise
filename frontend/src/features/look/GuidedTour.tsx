import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

import Logo from "../../components/Logo";
import { icons } from "../../components/icons";
import { Button } from "../../components/ui";
import { CHAPTERS } from "./tourChapters";

export default function GuidedTour({ onClose }: { onClose: (destination?: string) => void }) {
  const [index, setIndex] = useState(0);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const chapter = CHAPTERS[index];
  const last = index === CHAPTERS.length - 1;

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
    const targets = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not([disabled])"));
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
        className="kw-rise flex max-h-full w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-2xl sm:rounded-3xl dark:border-zinc-700 dark:bg-zinc-900"
      >
        <header className="flex shrink-0 items-center gap-3 border-b border-zinc-200 px-4 py-3 sm:px-6 dark:border-zinc-800">
          <Logo className="h-9 w-9 shrink-0" />
          <div className="min-w-0 flex-1">
            <h2 id="tour-name" className="font-semibold tracking-tight">Keptwise tutorial</h2>
            <p className="text-xs text-zinc-600 dark:text-zinc-400">Chapter {index + 1} of {CHAPTERS.length}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => onClose()}>Close tutorial</Button>
        </header>
        <div
          role="progressbar"
          aria-label="Tutorial progress"
          aria-valuemin={0}
          aria-valuemax={CHAPTERS.length}
          aria-valuenow={index + 1}
          className="h-1 shrink-0 bg-zinc-100 dark:bg-zinc-800"
        >
          <div className="h-full bg-indigo-600 transition-[width] motion-reduce:transition-none" style={{ width: (index + 1) * 100 / CHAPTERS.length + "%" }} />
        </div>
        <div className="grid min-h-0 flex-1 md:grid-cols-[13rem_minmax(0,1fr)]">
          <nav aria-label="Tutorial chapters" className="flex gap-1 overflow-x-auto border-b border-zinc-200 bg-zinc-50 p-2 md:block md:overflow-y-auto md:border-b-0 md:border-r md:p-3 dark:border-zinc-800 dark:bg-zinc-950/70">
            {CHAPTERS.map((entry, position) => (
              <Button key={entry.id} variant="ghost" size="sm" aria-current={index === position ? "step" : undefined}
                className={"mb-0.5 justify-start md:w-full " + (index === position ? "bg-indigo-50 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200" : "")}
                onClick={() => setIndex(position)}>
                <span className="h-4 w-4">{icons[entry.icon]}</span>
                {entry.name}
              </Button>
            ))}
          </nav>
          <div ref={contentRef} className="min-h-0 overflow-y-auto px-4 py-5 sm:p-7">
            <h3 ref={titleRef} tabIndex={-1} className="text-2xl font-semibold tracking-tight outline-none">{chapter.title}</h3>
            <p className="mt-2 max-w-prose text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{chapter.intro}</p>
            <div className="mt-5 grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(13rem,0.75fr)]">
              <ol className="space-y-3" aria-label="Steps to try">
                {chapter.steps.map(([label, instruction], position) => (
                  <li key={label} className="flex gap-3 rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-indigo-50 text-xs font-semibold text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{position + 1}</span>
                    <div>
                      <p className="text-sm font-semibold">{label}</p>
                      <p className="mt-1 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{instruction}</p>
                    </div>
                  </li>
                ))}
              </ol>
              <aside aria-label="Example" className="overflow-hidden rounded-2xl border border-indigo-100 bg-indigo-50/60 dark:border-indigo-950 dark:bg-indigo-950/30">
                <div className="border-b border-indigo-100 p-4 dark:border-indigo-950">
                  <span className="grid h-10 w-10 place-items-center rounded-xl bg-white p-2 text-indigo-700 shadow-sm dark:bg-zinc-900 dark:text-indigo-300">{icons[chapter.icon]}</span>
                  <p className="mt-3 text-xs font-medium text-indigo-700 dark:text-indigo-300">Example</p>
                  <h4 className="mt-0.5 text-sm font-semibold">{chapter.preview.title}</h4>
                </div>
                <dl className="space-y-2 p-3">
                  {chapter.preview.rows.map(([label, description]) => (
                    <div key={label + description} className="rounded-lg bg-white px-3 py-2 shadow-sm dark:bg-zinc-900">
                      <dt className="text-xs font-medium text-zinc-600 dark:text-zinc-400">{label}</dt>
                      <dd className="mt-0.5 text-sm">{description}</dd>
                    </div>
                  ))}
                </dl>
              </aside>
            </div>
          </div>
        </div>
        <footer className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-zinc-200 bg-white px-4 py-3 sm:px-6 dark:border-zinc-800 dark:bg-zinc-900">
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
