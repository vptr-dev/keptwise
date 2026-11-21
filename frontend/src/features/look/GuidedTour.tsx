import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "../../components/ui";
import { navigate } from "../../lib/router";
import { CHAPTERS } from "./tourChapters";

type Highlight = { left: number; top: number; right: number; bottom: number };

export default function GuidedTour({ onClose }: { onClose: () => void }) {
  const [index, setIndex] = useState(0);
  const [spot, setSpot] = useState<Highlight | null>(null);
  const [panelHeight, setPanelHeight] = useState(168);
  const guide = useRef<HTMLDivElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const chapter = CHAPTERS[index];
  const last = index === CHAPTERS.length - 1;

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && guide.current?.contains(document.activeElement)) {
        event.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  useEffect(() => {
    navigate(chapter.path);
    setSpot(null);
    title.current?.focus({ preventScroll: true });
    let frame = 0;
    let previous: Element | null = null;

    function position() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const target = document.querySelector(`[data-tour="${chapter.target}"]`);
        if (!target) {
          setSpot(null);
          return;
        }
        if (target !== previous) {
          previous = target;
          target.scrollIntoView?.({ block: "nearest" });
        }
        const box = target.getBoundingClientRect();
        const clip = target.closest("main")?.getBoundingClientRect();
        const next = {
          left: Math.max(4, (clip?.left ?? 0) + 4, box.left - 4),
          top: Math.max(4, (clip?.top ?? 0) + 4, box.top - 4),
          right: Math.min(window.innerWidth - 4, box.right + 4, (clip?.right ?? window.innerWidth) - 4),
          bottom: Math.min(window.innerHeight - 4, box.bottom + 4, (clip?.bottom ?? window.innerHeight) - 4),
        };
        setSpot(next.right > next.left && next.bottom > next.top ? next : null);
        if (guide.current) setPanelHeight(guide.current.offsetHeight || 168);
      });
    }
    const observe = new MutationObserver(position);
    const main = document.querySelector("main");
    if (main) observe.observe(main, { subtree: true, childList: true, attributes: true });
    window.addEventListener("resize", position);
    document.addEventListener("scroll", position, true);
    position();
    return () => {
      cancelAnimationFrame(frame);
      observe.disconnect();
      window.removeEventListener("resize", position);
      document.removeEventListener("scroll", position, true);
    };
  }, [chapter]);

  const width = Math.min(356, window.innerWidth - 24);
  const left = spot ? Math.max(12, Math.min(window.innerWidth - width - 12, spot.left)) : window.innerWidth - width - 12;
  const below = spot && spot.bottom + panelHeight + 22 <= window.innerHeight;
  const above = spot && spot.top >= panelHeight + 22;
  const top = below ? spot.bottom + 10 : above ? spot.top - panelHeight - 10 : undefined;

  return createPortal(
    <>
      {spot && <div aria-hidden="true" className="pointer-events-none fixed z-[81] rounded-xl border-2 border-indigo-500 ring-4 ring-indigo-500/20"
        style={{ left: spot.left, top: spot.top, width: spot.right - spot.left, height: spot.bottom - spot.top }} />}
      <section ref={guide} role="dialog" aria-label="Keptwise tutorial"
        className="fixed z-[82] rounded-2xl border border-zinc-200 bg-white p-4 shadow-xl dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
        style={{ left, width, top, bottom: top === undefined ? 12 : undefined }}>
        <div className="flex items-center justify-between gap-2 text-xs text-zinc-500 dark:text-zinc-400">
          <span role="progressbar" aria-label="Tutorial progress" aria-valuemin={1}
            aria-valuemax={CHAPTERS.length} aria-valuenow={index + 1}>{index + 1} of {CHAPTERS.length}</span>
          <Button variant="ghost" size="sm" onClick={onClose}>Close tutorial</Button>
        </div>
        <h2 ref={title} tabIndex={-1} className="mt-1 font-semibold outline-none">{chapter.title}</h2>
        <p className="mt-1 text-sm leading-snug text-zinc-600 dark:text-zinc-300">{chapter.text}</p>
        <div className="mt-3 flex justify-between gap-2">
          <Button size="sm" variant="ghost" disabled={index === 0} onClick={() => setIndex(index - 1)}>Back</Button>
          <Button size="sm" onClick={() => last ? onClose() : setIndex(index + 1)}>{last ? "Finish tutorial" : "Next"}</Button>
        </div>
      </section>
    </>,
    document.body,
  );
}
