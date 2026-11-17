// The folder picture used for a collection: its own colour when it has one,
// the accent colour otherwise. A back with a tab, a sheet of paper, and a
// front with a soft shine. Inside a `.kw-folder` element the front tips open
// and the paper slides up when you point at it (see index.css).
import { useId } from "react";

import { COLLECTION_ICONS } from "./collectionIcons";

const COLOR_TEXT: Record<string, string> = {
  violet: "text-violet-500",
  indigo: "text-indigo-500",
  blue: "text-blue-500",
  teal: "text-teal-500",
  emerald: "text-emerald-500",
  amber: "text-amber-500",
  rose: "text-rose-500",
  zinc: "text-zinc-400",
};

export default function FolderIcon({
  color,
  icon,
  collectionId,
  className = "h-12 w-14",
}: {
  color?: string | null;
  icon?: string | null; // a ready-made one, or "custom:<stamp>" for the user's own picture
  collectionId?: number;
  className?: string;
}) {
  const id = useId();
  const tint = color ? COLOR_TEXT[color] ?? "text-indigo-500" : "text-indigo-500";
  return (
    <svg viewBox="0 0 64 52" className={`${className} shrink-0 drop-shadow-[0_6px_8px_rgb(0_0_0/0.14)] ${tint}`} aria-hidden="true">
      <defs>
        <linearGradient id={`${id}-shine`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.34" />
          <stop offset="0.55" stopColor="#fff" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.14" />
        </linearGradient>
      </defs>
      {/* the back, with its tab */}
      <path d="M4 10a5 5 0 0 1 5-5h13.6a5 5 0 0 1 3.8 1.7L29.2 10H55a5 5 0 0 1 5 5v27a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z" fill="currentColor" opacity="0.5" />
      {/* a sheet of paper */}
      <rect className="kw-folder-paper" x="10" y="12.5" width="44" height="26" rx="3.5" fill="#fff" opacity="0.92" stroke="#000" strokeOpacity="0.16" strokeWidth="0.7" />
      {/* the front */}
      <g className="kw-folder-front">
        <rect x="4" y="19" width="56" height="28" rx="5.5" fill="currentColor" stroke="#000" strokeOpacity="0.14" strokeWidth="0.7" />
        <rect x="4" y="19" width="56" height="28" rx="5.5" fill={`url(#${id}-shine)`} />
        <path d="M10 21.4h44" stroke="#fff" strokeOpacity="0.4" strokeWidth="1" strokeLinecap="round" />
        {icon?.startsWith("custom:") && collectionId !== undefined && (
          /* the user's own picture, on a small card on the front */
          <>
            <clipPath id={`${id}-own`}>
              <rect x="21" y="22" width="22" height="22" rx="5" />
            </clipPath>
            <rect x="20.4" y="21.4" width="23.2" height="23.2" rx="5.6" fill="#fff" opacity="0.9" />
            <image
              href={`/api/collections/${collectionId}/icon?v=${icon.slice(7)}`}
              x="21"
              y="22"
              width="22"
              height="22"
              preserveAspectRatio="xMidYMid slice"
              clipPath={`url(#${id}-own)`}
              data-icon="custom"
            />
          </>
        )}
        {icon && COLLECTION_ICONS[icon] && (
          /* the collection's own picture, pressed into the front */
          <g transform="translate(23 24.5) scale(0.75)" fill="none" stroke="#000" strokeOpacity="0.5" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" data-icon={icon}>
            {COLLECTION_ICONS[icon].shape}
          </g>
        )}
      </g>
    </svg>
  );
}
