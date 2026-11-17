// A save's picture. Until it has loaded (and for saves with no picture yet)
// the tile shows the logo, greyed out, in a thin frame, so every tile in the
// grid has the same quiet look. The real picture fades in over it.
import { useState } from "react";

import Logo from "../../components/Logo";
import { formatDuration } from "../enrich/enrichApi";
import type { ItemCard } from "../sorting/sortingApi";

/** The stand-in for a picture: the logo in grey, inside a thin frame. */
export function NoPicture({ label, small = false }: { label?: string; small?: boolean }) {
  return (
    <div
      role={label ? "img" : undefined}
      aria-label={label}
      className="absolute inset-0 flex items-center justify-center rounded-[inherit] bg-zinc-100 ring-1 ring-inset ring-zinc-300 dark:bg-zinc-800/70 dark:ring-white/15"
    >
      <Logo mono className={`${small ? "w-1/2" : "w-1/3"} aspect-square max-w-14 text-zinc-400 opacity-60 dark:text-zinc-500`} />
    </div>
  );
}

export default function Thumb({
  item,
  className = "",
  showDuration = true,
}: {
  item: Pick<ItemCard, "id" | "platform" | "platform_name" | "has_thumbnail" | "duration_s">;
  className?: string;
  showDuration?: boolean;
}) {
  const [state, setState] = useState<"loading" | "shown" | "failed">("loading");
  const duration = showDuration ? formatDuration(item.duration_s) : null;
  const wanted = item.has_thumbnail && state !== "failed";
  return (
    <div className={`relative overflow-hidden ${className}`}>
      {(!wanted || state !== "shown") && <NoPicture label={wanted ? undefined : `No picture yet (${item.platform_name})`} />}
      {wanted && (
        <img
          src={`/api/items/${item.id}/thumbnail`}
          alt=""
          loading="lazy"
          draggable={false}
          onLoad={() => setState("shown")}
          onError={() => setState("failed")}
          className={`relative h-full w-full object-cover transition-opacity duration-300 ${state === "shown" ? "opacity-100" : "opacity-0"}`}
        />
      )}
      {duration && (
        <span className="absolute bottom-1.5 right-1.5 rounded-md bg-black/70 px-1.5 py-0.5 text-[11px] font-medium text-white">
          {duration}
        </span>
      )}
    </div>
  );
}
