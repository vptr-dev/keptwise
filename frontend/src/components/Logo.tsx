// The Keptwise logo: three bookmarks, one behind the other. The front one
// takes the accent colour; the two behind it stay grey. The same outline is
// in desktop/logo_art.py (program and taskbar icons).
import { useId } from "react";

// The front bookmark, in its own units.
const FRONT =
  "M0 130C0 88 24 70 60 62L296 0C322-6 343 12 343 38L343 386C343 402 332 404 324 398L186 292C180 287 176 287 170 292L22 433C14 441 0 440 0 428Z";
// Where each one sits, back to front, in a 640 x 640 square.
const PLACES = [
  [35, 19],
  [148, 100],
  [261, 181],
] as const;
const GAP = 36;

export default function Logo({ className = "h-8 w-8", mono = false }: { className?: string; mono?: boolean }) {
  const id = useId().replace(/:/g, "");
  const shape = (index: number, extra = {}) => <path d={FRONT} transform={`translate(${PLACES[index][0]} ${PLACES[index][1]})`} {...extra} />;
  // A see-through gap round each bookmark that is in front of another.
  const cut = (index: number) => shape(index, { fill: "black", stroke: "black", strokeWidth: GAP * 2, strokeLinejoin: "round" });
  const fills = mono
    ? ["fill-current opacity-40", "fill-current opacity-70", "fill-current"]
    : ["fill-zinc-300 dark:fill-zinc-700", "fill-zinc-400 dark:fill-[#8b8d91]", "fill-indigo-600 dark:fill-indigo-500"];
  return (
    <svg viewBox="0 0 640 640" className={className} aria-hidden="true" focusable="false">
      <defs>
        <mask id={`${id}-b`} maskUnits="userSpaceOnUse" x="0" y="0" width="640" height="640">
          <rect width="640" height="640" fill="white" />
          {cut(1)}
          {cut(2)}
        </mask>
        <mask id={`${id}-m`} maskUnits="userSpaceOnUse" x="0" y="0" width="640" height="640">
          <rect width="640" height="640" fill="white" />
          {cut(2)}
        </mask>
      </defs>
      {shape(0, { className: fills[0], mask: `url(#${id}-b)` })}
      {shape(1, { className: fills[1], mask: `url(#${id}-m)` })}
      {shape(2, { className: `${fills[2]} transition-[fill] duration-300` })}
    </svg>
  );
}
