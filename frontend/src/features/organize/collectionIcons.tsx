// The small pictures a collection's folder can carry, and the picker for them
// (in a collection's details and its right-click menu). Drawn as 24x24 line
// shapes; FolderIcon puts the chosen one on the folder's front.
import { useRef, type ReactNode } from "react";

export const COLLECTION_ICONS: Record<string, { label: string; shape: ReactNode }> = {
  star: { label: "Star", shape: <><path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.8-5.2 2.8 1-5.8-4.3-4.1 5.9-.9z" /></> },
  heart: { label: "Heart", shape: <><path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.4 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10z" /></> },
  book: { label: "Book", shape: <><path d="M5 4.5h10.5a3 3 0 0 1 3 3V20H8a3 3 0 0 1-3-3z" /><path d="M5 17a3 3 0 0 1 3-3h10.5" /></> },
  film: { label: "Film", shape: <><rect x="3.5" y="5" width="17" height="14" rx="2.5" /><path d="M10 9.2v5.6l4.8-2.8z" /></> },
  music: { label: "Music", shape: <><path d="M9 17.5V6l10-2v11.5" /><circle cx="6.5" cy="17.5" r="2.5" /><circle cx="16.5" cy="15.5" r="2.5" /></> },
  food: { label: "Food", shape: <><path d="M7 3.5v7M4.5 3.5V8a2.5 2.5 0 0 0 5 0V3.5M7 10.5v10" /><path d="M17 20.5v-7h-2.5V8a4.5 4.5 0 0 1 2.5-4.5z" /></> },
  plane: { label: "Travel", shape: <><path d="M21 3.5L3.5 10.5l6.5 2.5 2.5 6.5z" /><path d="M10 13l4-4" /></> },
  home: { label: "Home", shape: <><path d="M4 11l8-7 8 7" /><path d="M6 9.5V20h12V9.5" /><path d="M10 20v-5.5h4V20" /></> },
  cart: { label: "Shopping", shape: <><path d="M3.5 5h2.5l2.2 10h9.3l2-7.5H7" /><circle cx="9.5" cy="19" r="1.3" /><circle cx="17" cy="19" r="1.3" /></> },
  game: { label: "Games", shape: <><rect x="2.5" y="7.5" width="19" height="10" rx="5" /><path d="M7.5 10.5v4M5.5 12.5h4M15.5 11.5h.01M18 13.5h.01" /></> },
  fitness: { label: "Fitness", shape: <><path d="M7 8v8M4 10v4M17 8v8M20 10v4M7 12h10" /></> },
  code: { label: "Code", shape: <><path d="M8.5 8l-4.5 4 4.5 4M15.5 8l4.5 4-4.5 4M13.5 5.5l-3 13" /></> },
  idea: { label: "Ideas", shape: <><path d="M9 17.5h6M10 20.5h4" /><path d="M12 3.5a6 6 0 0 0-3.5 10.900V17h7v-2.6A6 6 0 0 0 12 3.5z" /></> },
  camera: { label: "Camera", shape: <><path d="M4 8h3.2l1.5-2.5h6.6L16.8 8H20v11H4z" /><circle cx="12" cy="13.3" r="3.3" /></> },
  work: { label: "Work", shape: <><rect x="3.5" y="7.5" width="17" height="12" rx="2.5" /><path d="M9 7.5V5.5h6v2M3.5 12.5h17" /></> },
  money: { label: "Money", shape: <><circle cx="12" cy="12" r="8.5" /><path d="M14.5 9.3c-.5-.9-1.4-1.3-2.5-1.3-1.5 0-2.6.8-2.6 2s1 1.700 2.6 2 2.700.8 2.700 2.1-1.2 2-2.700 2c-1.2 0-2.2-.5-2.700-1.4M12 6.5V8M12 16.1v1.4" /></> },
  leaf: { label: "Nature", shape: <><path d="M5 19c0-9 5-14 15-14 0 10-5 15-14 14z" /><path d="M5 19l8-8" /></> },
  pin: { label: "Places", shape: <><path d="M12 21s6.5-5.700 6.5-11a6.5 6.5 0 0 0-13 0c0 5.3 6.5 11 6.5 11z" /><circle cx="12" cy="10" r="2.3" /></> },
};

const MAX_FILE_BYTES = 2_500_000;

/** Read a chosen picture file as a data address ("data:image/png;base64,..."). */
export function readPicture(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) return reject(new Error("That isn't a picture. Choose a PNG, JPG, WebP or GIF file."));
    if (file.size > MAX_FILE_BYTES) return reject(new Error("That picture is too big. Choose one under 2.5 MB."));
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("That file couldn't be read."));
    reader.readAsDataURL(file);
  });
}

/** Choose a ready-made icon, none, or (with onUpload) a picture of your own. */
export function IconPicker({
  value,
  onPick,
  onUpload,
}: {
  value: string | null | undefined;
  onPick: (icon: string | null) => void;
  onUpload?: (file: File) => void;
}) {
  const file = useRef<HTMLInputElement>(null);
  const own = !!value?.startsWith("custom:");
  const tile = (chosen: boolean) =>
    `kw-btn flex h-8 w-8 items-center justify-center rounded-lg border p-1.5 ${
      chosen
        ? "border-indigo-600 bg-indigo-600 text-white"
        : "border-zinc-200 text-zinc-600 hover:border-zinc-300 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-300 dark:hover:text-white"
    }`;
  return (
    <div role="radiogroup" aria-label="Icon" className="flex flex-wrap gap-1.5">
      <button type="button" role="radio" aria-checked={!value} aria-label="No icon" title="Plain folder" onClick={() => onPick(null)} className={tile(!value)}>
        <svg viewBox="0 0 24 24" className="h-full w-full" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />
        </svg>
      </button>
      {onUpload && (
        <>
          <button
            type="button"
            role="radio"
            aria-checked={own}
            aria-label="Your own picture"
            title={own ? "Your own picture (click to choose another)" : "Use a picture of your own"}
            onClick={() => file.current?.click()}
            className={`${tile(own)} w-auto gap-1.5 px-2 text-xs font-medium`}
          >
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 16V5M7.5 9.5L12 5l4.5 4.5M5 19h14" />
            </svg>
            {own ? "Change picture" : "Upload"}
          </button>
          <input
            ref={file}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            aria-label="Choose a picture for this collection"
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              event.target.value = ""; // so the same file can be chosen again
              if (chosen) onUpload(chosen);
            }}
          />
        </>
      )}
      {Object.entries(COLLECTION_ICONS).map(([name, icon]) => (
        <button key={name} type="button" role="radio" aria-checked={value === name} aria-label={icon.label} title={icon.label} onClick={() => onPick(name)} className={tile(value === name)}>
          <svg viewBox="0 0 24 24" className="h-full w-full" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {icon.shape}
          </svg>
        </button>
      ))}
    </div>
  );
}
