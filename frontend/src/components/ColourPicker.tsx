// The one colour picker the whole app uses (collections, spaces, tags, plans
// and the app's accent): "Accent colour" (or "Default" for the accent itself)
// at the top, the colours below, and the ones picked lately at the bottom.
import { useState } from "react";

import { icons } from "./icons";
import Popover from "./Popover";

// Fixed colours, never shifted by the accent (Tailwind's 500 shades).
export const COLOUR_HEX: Record<string, string> = {
  violet: "#8b5cf6",
  indigo: "#6366f1",
  blue: "#3b82f6",
  teal: "#14b8a6",
  emerald: "#10b981",
  amber: "#f59e0b",
  rose: "#f43f5e",
  zinc: "#a1a1aa",
};
export const COLOUR_NAMES: Record<string, string> = {
  violet: "Violet",
  indigo: "Indigo",
  blue: "Blue",
  teal: "Teal",
  emerald: "Green",
  amber: "Amber",
  rose: "Rose",
  zinc: "Grey",
};
const RECENT_KEY = "kw-recent-colours";
const RECENT_KEPT = 6;

function readRecent(): string[] {
  try {
    const list = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(list) ? list.filter((c) => typeof c === "string" && c in COLOUR_HEX) : [];
  } catch {
    return [];
  }
}

function remember(colour: string) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify([colour, ...readRecent().filter((c) => c !== colour)].slice(0, RECENT_KEPT)));
  } catch {
    // no storage: nothing to remember
  }
}

/** A round swatch. null/"accent": the accent colour (follows the app's choice). */
export function Swatch({ colour, className = "h-3 w-3" }: { colour: string | null | undefined; className?: string }) {
  const hex = colour ? COLOUR_HEX[colour] : undefined;
  return (
    <span
      className={`inline-block shrink-0 rounded-full ${hex ? "" : "bg-indigo-500"} ${className}`}
      style={hex ? { backgroundColor: hex } : undefined}
      aria-hidden="true"
    />
  );
}

export function colourLabel(colour: string | null | undefined, accentLabel = "Accent colour"): string {
  return colour && colour in COLOUR_HEX ? COLOUR_NAMES[colour] : accentLabel;
}

export default function ColourPicker({
  value,
  onPick,
  accentLabel = "Accent colour",
  accentHint = "Follows the app's accent colour",
  accentSwatch,
  colours = Object.keys(COLOUR_HEX),
}: {
  value: string | null | undefined; // null or "accent": the accent option
  onPick: (colour: string | null) => void;
  accentLabel?: string;
  accentHint?: string;
  accentSwatch?: React.ReactNode;
  colours?: string[];
}) {
  const [recent] = useState(readRecent);
  const isAccent = !value || value === "accent" || value === "default";
  const pick = (colour: string | null) => {
    if (colour) remember(colour);
    onPick(colour);
  };
  const dot = (colour: string, size = "h-8 w-8") => {
    const chosen = value === colour;
    return (
      <button
        key={colour}
        type="button"
        role="radio"
        aria-checked={chosen}
        aria-label={COLOUR_NAMES[colour] ?? colour}
        title={COLOUR_NAMES[colour] ?? colour}
        onClick={() => pick(colour)}
        className={`flex ${size} items-center justify-center rounded-full text-white ring-offset-2 ring-offset-white transition focus-visible:outline-2 focus-visible:outline-indigo-500 dark:ring-offset-zinc-900 ${
          chosen ? "ring-2 ring-zinc-900 dark:ring-white" : "hover:scale-110"
        }`}
        style={{ backgroundColor: COLOUR_HEX[colour] }}
      >
        {chosen && <span className="h-4 w-4">{icons.check}</span>}
      </button>
    );
  };
  return (
    <div className="space-y-3 p-1" role="radiogroup" aria-label="Colour">
      <button
        type="button"
        role="radio"
        aria-checked={isAccent}
        onClick={() => pick(null)}
        className={`flex w-full items-center gap-3 rounded-xl px-2.5 py-2 text-left text-sm transition ${
          isAccent ? "bg-zinc-900/5 font-medium dark:bg-white/10" : "hover:bg-zinc-900/5 dark:hover:bg-white/5"
        }`}
      >
        {accentSwatch ?? <Swatch colour={null} className="h-6 w-6" />}
        <span className="min-w-0 flex-1">
          <span className="block">{accentLabel}</span>
          <span className="block text-xs font-normal text-zinc-500 dark:text-zinc-400">{accentHint}</span>
        </span>
        {isAccent && <span className="h-4 w-4 text-zinc-500">{icons.check}</span>}
      </button>
      <div className="grid grid-cols-4 justify-items-center gap-2.5 px-1">{colours.map((c) => dot(c))}</div>
      {recent.length > 0 && (
        <div className="border-t border-zinc-900/5 px-1 pt-2.5 dark:border-white/10">
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">Recently used</p>
          <div className="flex gap-2">{recent.filter((c) => colours.includes(c)).map((c) => dot(c, "h-6 w-6"))}</div>
        </div>
      )}
    </div>
  );
}

/** A button showing the current colour that opens the picker. */
export function ColourButton({
  value,
  onPick,
  label = "Colour",
  accentLabel,
}: {
  value: string | null | undefined;
  onPick: (colour: string | null) => void;
  label?: string;
  accentLabel?: string;
}) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  return (
    <>
      <button
        type="button"
        onClick={(event) => setAnchor(anchor ? null : event.currentTarget)}
        aria-label={`${label}: ${colourLabel(value, accentLabel)}. Change`}
        className="inline-flex items-center gap-2 rounded-lg border border-zinc-900/10 px-2.5 py-1.5 text-sm hover:bg-zinc-900/5 dark:border-white/10 dark:hover:bg-white/5"
      >
        <Swatch colour={value === "accent" ? null : value} className="h-4 w-4" />
        {colourLabel(value, accentLabel)}
        <span className="h-3.5 w-3.5 text-zinc-400">{icons.down}</span>
      </button>
      {anchor && (
        <Popover anchor={anchor} onClose={() => setAnchor(null)} label={label} width={232}>
          <ColourPicker
            value={value}
            accentLabel={accentLabel}
            onPick={(colour) => {
              setAnchor(null);
              onPick(colour);
            }}
          />
        </Popover>
      )}
    </>
  );
}
