// How the app looks: light/dark theme, accent colour, text size, and a few
// personal touches. The choices are saved by the backend (the app window keeps
// no browser storage), and "system" follows the Windows setting live.
import { useCallback, useEffect, useState } from "react";
import { flushSync } from "react-dom";

import { api } from "./api";

export type ThemeChoice = "system" | "light" | "dark";
export type Accent = "default" | "violet" | "indigo" | "blue" | "teal" | "emerald" | "rose" | "amber";
export type TextSize = "small" | "normal" | "large";
export type StartPage = "library" | "collections" | "tags" | "plans" | "chat" | "unsave";

export type Look = {
  theme: ThemeChoice;
  accent: Accent;
  text_size: TextSize;
  start_page: StartPage;
  name: string;
  compact_sidebar: boolean;
  nav_order: string[]; // page paths in the order the sidebar shows them
  nav_hidden: string[]; // pages left out of the sidebar
  sidebar_collections: boolean; // the collections tree under the pages
  sidebar_tags: boolean; // the most used tags under that
  sidebar_folded: string[]; // "collections" and/or "tags" folded away
  card_size: "small" | "medium" | "large"; // Library pictures
  dismissed_tips: string[]; // tips the user closed
  card_actions: boolean; // quick buttons on a card when the mouse is over it
  welcomed?: boolean; // the first-run setup is done (false: show it)
  look_version?: number; // kept by the backend
};

export const DEFAULT_LOOK: Look = {
  theme: "system",
  accent: "default",
  text_size: "normal",
  start_page: "library",
  name: "",
  compact_sidebar: false,
  nav_order: [],
  nav_hidden: [],
  sidebar_collections: true,
  sidebar_tags: true,
  sidebar_folded: [],
  card_size: "medium",
  dismissed_tips: [],
  card_actions: true,
};

export const THEME_LABELS: Record<ThemeChoice, string> = {
  system: "Same as Windows",
  light: "Light",
  dark: "Dark",
};

// The swatch colour shown for each accent in Settings. "Default" has no
// colour of its own: it is dark in light mode and light in dark mode.
export const ACCENTS: { value: Accent; label: string; swatch: string | null }[] = [
  { value: "default", label: "Default", swatch: null },
  { value: "violet", label: "Violet", swatch: "#7c3aed" },
  { value: "indigo", label: "Indigo", swatch: "#4f46e5" },
  { value: "blue", label: "Blue", swatch: "#2563eb" },
  { value: "teal", label: "Teal", swatch: "#0d9488" },
  { value: "emerald", label: "Green", swatch: "#059669" },
  { value: "rose", label: "Rose", swatch: "#e11d48" },
  { value: "amber", label: "Amber", swatch: "#d97706" },
];

export const TEXT_SIZE_LABELS: Record<TextSize, string> = { small: "Small", normal: "Normal", large: "Large" };

export const START_PAGE_LABELS: Record<StartPage, string> = {
  library: "Library",
  collections: "Collections",
  tags: "Tags",
  plans: "Plans",
  chat: "AI Assistant",
  unsave: "Unsave",
};

function windowsIsDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Put the right theme on the page right now. */
export function applyTheme(choice: ThemeChoice): void {
  const dark = choice === "dark" || (choice === "system" && windowsIsDark());
  document.documentElement.classList.toggle("dark", dark);
}

/** Put the accent colour and text size on the page (see index.css). */
export function applyLook(look: Look): void {
  applyTheme(look.theme);
  document.documentElement.dataset.accent = look.accent;
  document.documentElement.dataset.textSize = look.text_size;
  tellDesktop(look.accent);
}

/** The desktop window tints its taskbar icon to match (nothing in a browser). */
let lastTold = "";
function tellDesktop(accent: Accent): void {
  const dark = document.documentElement.classList.contains("dark");
  const now = `${accent}|${dark}`;
  const desktop = (window as { pywebview?: { api?: { set_accent?: (accent: string, dark: boolean) => Promise<boolean> } } }).pywebview?.api;
  if (now === lastTold || !desktop?.set_accent) return;
  lastTold = now;
  desktop.set_accent(accent, dark).catch(() => undefined);
}

/** The page stays hidden until the saved look is on it, so the app never
 * opens in one accent and then jumps to another. */
function showPage(): void {
  document.documentElement.dataset.look = "ready";
}

export type Point = { x: number; y: number };

/** Where the theme button is on screen (the middle of the window without one). */
export function themeButtonSpot(): Point {
  const box = document.querySelector("[data-theme-button]")?.getBoundingClientRect();
  if (box && box.width > 0) return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
  return { x: window.innerWidth / 2, y: window.innerHeight / 2 };
}

/** Make a change of theme and let the new look spread out in a circle from
 * `from` (the button pressed). Where the window can't do that, or Windows is
 * set to reduce motion, the change simply happens. */
export function revealTheme(change: () => void, from: Point = themeButtonSpot()): void {
  const doc = document as Document & { startViewTransition?: (update: () => void) => { ready: Promise<void> } };
  const calm = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (typeof doc.startViewTransition !== "function" || calm) {
    change();
    return;
  }
  const reach = Math.hypot(Math.max(from.x, window.innerWidth - from.x), Math.max(from.y, window.innerHeight - from.y));
  const transition = doc.startViewTransition(() => flushSync(change));
  transition.ready
    .then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${from.x}px ${from.y}px)`, `circle(${reach}px at ${from.x}px ${from.y}px)`] },
        { duration: 520, easing: "cubic-bezier(0.4, 0, 0.2, 1)", pseudoElement: "::view-transition-new(root)" },
      );
    })
    .catch(() => undefined);
}

/** Light -> Dark -> Same as Windows -> Light ... (the sidebar button and Ctrl+Shift+L). */
export function nextTheme(choice: ThemeChoice): ThemeChoice {
  return choice === "light" ? "dark" : choice === "dark" ? "system" : "light";
}

export function useLook() {
  const [look, setLookState] = useState<Look>(DEFAULT_LOOK);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    applyLook(DEFAULT_LOOK); // until the saved choice arrives
    api
      .get<Partial<Look>>("/api/ui")
      .then((saved) => {
        const start = (saved.start_page as string) === "home" ? "library" : saved.start_page; // Home was removed
        setLookState({ ...DEFAULT_LOOK, ...saved, start_page: start ?? DEFAULT_LOOK.start_page });
      })
      .catch(() => undefined) // keep the defaults
      .finally(() => {
        setLoaded(true);
        window.setTimeout(showPage, 0); // after the look is applied (a timer, since a hidden window draws no frames)
      });
  }, []);

  useEffect(() => {
    // The desktop window's controls can arrive after the first look is applied.
    const again = () => tellDesktop(look.accent);
    window.addEventListener("pywebviewready", again);
    return () => window.removeEventListener("pywebviewready", again);
  }, [look.accent]);

  useEffect(() => {
    applyLook(look);
    if (look.theme !== "system" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const follow = () => applyTheme("system");
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, [look]);

  /** Change some choices and save them. */
  const changeLook = useCallback((change: Partial<Look>) => {
    setLookState((old) => {
      const next = { ...old, ...change };
      api.put("/api/ui", next).catch(() => undefined);
      return next;
    });
  }, []);

  return { look, loaded, changeLook };
}
