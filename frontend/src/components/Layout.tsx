// The app frame: sidebar on the left (logo and the Search button, the platform
// picker, then the pages in two sections, Organise and Manage), the page on
// the right. The sidebar and top strip are frosted glass over the backdrop.
// The window has no Windows title bar: the top strip (window buttons) and the
// logo corner are where the window is dragged from.
// Pages can be dragged into another order within their section.
import { useState, type DragEvent, type ReactNode } from "react";

import Logo from "./Logo";
import { NAV_DRAG } from "../features/organize/organizeApi";
import { movedNav } from "../features/organize/tree";
import { THEME_LABELS, type ThemeChoice } from "../lib/theme";
import { icons } from "./icons";
import { ResizeEdges, WindowButtons, toggleMaximizeOnDoubleClick, useDesktopWindow } from "./WindowControls";

const THEME_ICONS: Record<ThemeChoice, ReactNode> = { light: icons.sun, dark: icons.moon, system: icons.monitor };
// pywebview drags the window from elements with this class (not from what's inside them).
const DRAG = "pywebview-drag-region";

export type NavItem = {
  path: string; // "/library"
  label: string;
  icon: ReactNode;
  badge?: number;
  badgeTone?: "indigo" | "amber";
};

export type NavSection = { id: string; title: string; items: NavItem[] };

/** What the sidebar's bottom corner says, kept up to date by the app. */
export type LiveStatus = {
  connected: boolean;
  aiLabel: string;
  aiReady: boolean | null; // null: not checked yet
  aiMessage?: string | null; // why it isn't ready
  checkedAt?: Date | null;
};

const SMALL_BUTTON =
  "flex h-7 w-7 items-center justify-center rounded-md p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:hover:bg-zinc-800 dark:hover:text-zinc-100";

export default function Layout({
  sections,
  activePath,
  status,
  children,
  footer,
  topBar,
  actions,
  onSearch,
  picker,
  theme,
  compact = false,
  onCycleTheme,
  onShortcuts,
  onReorderNav,
  onStatusClick,
}: {
  sections: NavSection[];
  activePath: string;
  status: LiveStatus;
  children: ReactNode;
  footer?: ReactNode;
  topBar?: ReactNode; // something to show above the page (nothing by default)
  actions?: ReactNode; // buttons at the top right (Undo and Redo)
  onSearch?: () => void; // open the command centre
  picker?: ReactNode; // the platform drop-down, top left
  theme?: ThemeChoice;
  compact?: boolean; // icons-only sidebar
  onCycleTheme?: () => void;
  onShortcuts?: () => void;
  onReorderNav?: (paths: string[]) => void; // every page, in the new order
  onStatusClick?: () => void; // open the AI settings
}) {
  const desktop = useDesktopWindow();
  const onDoubleClick = toggleMaximizeOnDoubleClick(desktop);
  const [dropHint, setDropHint] = useState<{ path: string; after: boolean } | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const sectionOf = (path: string) => sections.find((s) => s.items.some((i) => i.path === path))?.id;

  function dragOver(event: DragEvent<HTMLElement>, path: string) {
    if (!onReorderNav || !event.dataTransfer.types.includes(NAV_DRAG)) return;
    if (dragging && sectionOf(dragging) !== sectionOf(path)) return; // pages stay in their own section
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const box = event.currentTarget.getBoundingClientRect();
    setDropHint({ path, after: event.clientY > box.top + box.height / 2 });
  }

  function drop(event: DragEvent<HTMLElement>, path: string) {
    const from = event.dataTransfer.getData(NAV_DRAG);
    setDropHint(null);
    if (!from || !onReorderNav || sectionOf(from) !== sectionOf(path)) return;
    event.preventDefault();
    const after = dropHint?.path === path ? dropHint.after : false;
    const all = sections.flatMap((s) => s.items.map((item) => item.path));
    onReorderNav(movedNav(all, from, path, after));
  }

  const aiDot = status.aiReady === null ? "bg-zinc-400" : status.aiReady ? "bg-emerald-500" : "bg-amber-500";

  return (
    <div className="flex h-screen text-zinc-900 dark:text-zinc-100">
      <aside
        className={`kw-glass flex shrink-0 flex-col border-r border-zinc-200 bg-white transition-[width] dark:border-zinc-800 dark:bg-zinc-900 ${
          compact ? "w-16" : "w-60"
        }`}
      >
        <div
          className={`${DRAG} flex h-14 shrink-0 items-center gap-2.5 ${compact ? "justify-center px-2" : "px-3"}`}
          onDoubleClick={onDoubleClick}
        >
          <Logo className="pointer-events-none h-8 w-8 shrink-0" />
          {!compact && onSearch && (
            <button
              type="button"
              onClick={onSearch}
              aria-label="Search and commands"
              title="Search your saves, or do something (Ctrl+K)"
              className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-xl border border-zinc-900/10 bg-white/50 px-2.5 text-sm text-zinc-500 transition hover:border-zinc-900/20 hover:bg-white/80 hover:text-zinc-800 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:border-white/10 dark:bg-white/5 dark:text-zinc-400 dark:hover:border-white/20 dark:hover:bg-white/10 dark:hover:text-zinc-100"
            >
              <span className="h-4 w-4 shrink-0">{icons.search}</span>
              <span className="flex-1 truncate text-left">Search</span>
              <kbd className="rounded-md border border-zinc-900/10 px-1.5 py-0.5 text-[10px] dark:border-white/15">Ctrl K</kbd>
            </button>
          )}
        </div>
        {compact && onSearch && (
          <div className="flex justify-center px-2 pb-2">
            <button type="button" onClick={onSearch} aria-label="Search and commands" title="Search and commands (Ctrl+K)" className={`${SMALL_BUTTON} h-10 w-10 rounded-xl p-2.5`}>
              {icons.search}
            </button>
          </div>
        )}
        {picker && <div className={`pb-2 ${compact ? "px-2" : "px-3"}`}>{picker}</div>}
        <div
          className={`kw-quiet-scroll flex-1 overflow-y-auto pt-1 ${compact ? "px-2" : "px-3"}`}
          onDragLeave={(e) => !e.currentTarget.contains(e.relatedTarget as Node) && setDropHint(null)}
        >
          {sections.map((section, index) => (
            <nav key={section.id} aria-label={section.title} className={index > 0 ? "mt-4" : ""}>
              {compact ? (
                index > 0 && <div className="mx-2 mb-3 border-t border-zinc-200 dark:border-zinc-800" aria-hidden="true" />
              ) : (
                <h2 className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
                  {section.title}
                </h2>
              )}
              <div className={compact ? "space-y-1" : "space-y-0.5"}>
                {section.items.map((item) => {
                  const active = activePath === item.path || activePath.startsWith(`${item.path}/`);
                  const hint =
                    dropHint?.path === item.path && dragging !== item.path ? (dropHint.after ? "after" : "before") : null;
                  return (
                    <a
                      key={item.path}
                      href={`#${item.path}`}
                      draggable={!!onReorderNav}
                      onDragStart={(event) => {
                        event.dataTransfer.setData(NAV_DRAG, item.path);
                        event.dataTransfer.effectAllowed = "move";
                        setDragging(item.path);
                      }}
                      onDragEnd={() => {
                        setDragging(null);
                        setDropHint(null);
                      }}
                      onDragOver={(event) => dragOver(event, item.path)}
                      onDrop={(event) => drop(event, item.path)}
                      aria-current={active ? "page" : undefined}
                      aria-label={compact ? item.label : undefined}
                      title={compact ? item.label : onReorderNav ? "Drag to move" : undefined}
                      className={`relative flex items-center gap-3 text-sm font-medium transition active:scale-[0.98] ${
                        compact ? "mx-auto h-10 w-10 justify-center rounded-xl" : "rounded-lg px-3 py-2"
                      } ${dragging === item.path ? "opacity-40" : ""} ${
                        active
                          ? "bg-indigo-500/12 text-indigo-700 shadow-[inset_0_0_0_1px_rgb(0_0_0/0.04)] dark:bg-indigo-400/15 dark:text-indigo-200 dark:shadow-[inset_0_0_0_1px_rgb(255_255_255/0.06)]"
                          : "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
                      }`}
                    >
                      {hint === "before" && <span className="absolute inset-x-1 -top-px h-0.5 rounded bg-indigo-500" aria-hidden="true" />}
                      {hint === "after" && <span className="absolute inset-x-1 -bottom-px h-0.5 rounded bg-indigo-500" aria-hidden="true" />}
                      <span className={`shrink-0 ${compact ? "h-5 w-5" : "h-4 w-4"}`}>{item.icon}</span>
                      {!compact && <span className="flex-1">{item.label}</span>}
                      {item.badge ? (
                        <span
                          className={`rounded-full px-1.5 text-xs text-white ${
                            item.badgeTone === "amber" ? "bg-amber-500" : "bg-indigo-600"
                          } ${compact ? "absolute -right-0.5 -top-0.5 min-w-4 text-center text-[10px] leading-4" : ""}`}
                        >
                          {item.badge}
                        </span>
                      ) : null}
                    </a>
                  );
                })}
              </div>
            </nav>
          ))}
        </div>
        {!compact && footer}
        <div className={`border-t border-zinc-200 py-3 text-xs dark:border-zinc-800 ${compact ? "px-2" : "px-5"}`}>
          {!compact && (
            <button
              type="button"
              onClick={onStatusClick}
              className="-mx-2 block w-[calc(100%+1rem)] rounded-md px-2 py-1 text-left hover:bg-zinc-100 dark:hover:bg-zinc-800"
              title={status.checkedAt ? `Checked at ${status.checkedAt.toLocaleTimeString()}` : undefined}
            >
              <p className="flex items-center gap-2 text-zinc-600 dark:text-zinc-400" role="status">
                <span className={`h-2 w-2 rounded-full ${status.connected ? "bg-emerald-500" : "bg-red-500"}`} aria-hidden="true" />
                {status.connected ? "Backend connected" : "Backend not reachable"}
              </p>
              <p className="mt-0.5 flex items-center gap-2 truncate text-zinc-500" title={status.aiMessage ?? status.aiLabel}>
                <span className={`h-2 w-2 shrink-0 rounded-full ${status.connected ? aiDot : "bg-zinc-400"}`} aria-hidden="true" />
                <span className="truncate">AI: {status.aiLabel}</span>
              </p>
              {status.connected && status.aiReady === false && status.aiMessage && (
                <p className="mt-0.5 line-clamp-2 pl-4 text-[11px] text-amber-700 dark:text-amber-400">{status.aiMessage}</p>
              )}
            </button>
          )}
          <div className={`flex items-center gap-1 ${compact ? "flex-col" : "mt-2"}`}>
            {compact && (
              <span
                className={`mb-1 h-2 w-2 rounded-full ${status.connected ? aiDot : "bg-red-500"}`}
                title={status.connected ? `AI: ${status.aiLabel}` : "Backend not reachable"}
                aria-hidden="true"
              />
            )}
            {theme && onCycleTheme && (
              <button
                type="button"
                onClick={onCycleTheme}
                data-theme-button
                title={`Theme: ${THEME_LABELS[theme]} (Ctrl+Shift+L to switch)`}
                aria-label={`Theme: ${THEME_LABELS[theme]}. Switch theme`}
                className={SMALL_BUTTON}
              >
                {THEME_ICONS[theme]}
              </button>
            )}
            {onShortcuts && (
              <button type="button" onClick={onShortcuts} title="Keyboard shortcuts (?)" aria-label="Keyboard shortcuts" className={SMALL_BUTTON}>
                {icons.keyboard}
              </button>
            )}
          </div>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {(desktop || topBar || actions) && (
          <header className={`${DRAG} flex h-10 shrink-0 items-stretch gap-3 pl-4 ${desktop ? "" : "pr-3"}`} onDoubleClick={onDoubleClick}>
            <div className="min-w-0 flex-1 self-center">{topBar}</div>
            {actions}
            {desktop && <WindowButtons desktop={desktop} />}
          </header>
        )}
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>
      {desktop && <ResizeEdges desktop={desktop} />}
    </div>
  );
}
