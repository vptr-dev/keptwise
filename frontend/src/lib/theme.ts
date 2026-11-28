// How the app looks: light/dark theme, accent colour, text size, and a few
// personal touches. The choices are saved by the backend (the app window keeps
// no browser storage), and "system" follows the Windows setting live.
import { useCallback, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { toast } from "../components/Toasts";
import { api, errorText } from "./api";

export type BackgroundStyle = "clear" | "glass" | "mica" | "solid";
export const BACKGROUND_LABELS: Record<BackgroundStyle, string> = { clear: "Clear", glass: "Glass", mica: "Mica", solid: "Solid" };
export const UNSAVE_SHORTCUT_LABELS = {
  off: "Off", "ctrl-alt-u": "Ctrl+Alt+U", "ctrl-alt-n": "Ctrl+Alt+N", "ctrl-shift-f9": "Ctrl+Shift+F9",
};
export type UnsaveShortcut = keyof typeof UNSAVE_SHORTCUT_LABELS;

export type ThemeChoice = "system" | "light" | "dark";
export type Accent = "default" | "violet" | "indigo" | "blue" | "teal" | "emerald" | "rose" | "amber";
export type TextSize = "small" | "normal" | "large";
export type StartPage = "library" | "collections" | "tags" | "plans" | "chat" | "unsave";

export type Look = {
  theme: ThemeChoice;
  background?: BackgroundStyle;
  unsave_shortcut?: UnsaveShortcut;
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
  tutorial_seen?: boolean;
  hide_sort_stats?: boolean;
  hide_tips?: boolean; // no tips, blurbs or descriptions (Settings -> Appearance)
  look_version?: number; // kept by the backend
};

export const DEFAULT_LOOK: Look = {
  theme: "system",
  background: "mica",
  unsave_shortcut: "off",
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

let backdropSequence = 0;

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
  document.documentElement.dataset.background = look.background ?? "mica";
  document.documentElement.dataset.accent = look.accent;
  document.documentElement.dataset.tips = look.hide_tips ? "off" : "on";
  document.documentElement.dataset.textSize = look.text_size;
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
  const latest = useRef(look);
  const pending = useRef(Promise.resolve());

  useEffect(() => {
    applyLook(DEFAULT_LOOK); // until the saved choice arrives
    api
      .get<Partial<Look>>("/api/ui")
      .then((saved) => {
        const start = (saved.start_page as string) === "home" ? "library" : saved.start_page; // Home was removed
        latest.current = { ...DEFAULT_LOOK, ...saved, start_page: start ?? DEFAULT_LOOK.start_page };
        setLookState(latest.current);
      })
      .catch(() => undefined) // keep the defaults
      .finally(() => {
        setLoaded(true);
        window.setTimeout(showPage, 0); // after the look is applied (a timer, since a hidden window draws no frames)
      });
  }, []);

  useEffect(() => {
    applyLook(look);
    if (look.theme !== "system" || typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const follow = () => applyTheme("system");
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, [look]);

  useEffect(() => {
    const root = document.documentElement;
    const style = look.background ?? "mica";
    let request = 0;
    const apply = () => {
      const bridge = (window as Window & { pywebview?: { api?: {
        appearance?: (style: BackgroundStyle, dark: boolean, sequence: number) => Promise<boolean>;
      } } }).pywebview?.api;
      const current = ++request;
      root.removeAttribute("data-native-backdrop");
      void bridge?.appearance?.(style, root.classList.contains("dark"), ++backdropSequence).then(native => {
        if (current === request && native) root.dataset.nativeBackdrop = "on";
      }).catch(() => undefined);
    };
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    apply();
    window.addEventListener("pywebviewready", apply);
    if (look.theme === "system") media?.addEventListener("change", apply);
    return () => {
      request++;
      window.removeEventListener("pywebviewready", apply);
      media?.removeEventListener("change", apply);
    };
  }, [look.background, look.theme]);

  /** Change some choices and save them. */
  const changeLook = useCallback((change: Partial<Look>) => {
    const next = { ...latest.current, ...change };
    latest.current = next;
    setLookState(next);
    pending.current = pending.current.then(async () => {
      try {
        await api.put("/api/ui", next);
      } catch (error) {
        if (latest.current === next) toast("Couldn’t save your appearance settings. " + errorText(error), { tone: "error" });
      }
    });
  }, []);

  return { look, loaded, changeLook };
}
