// Settings -> Appearance: theme, accent colour, text size, start screen,
// your name, the sidebar (pages and their order), cards and closed tips.
// Every change is saved straight away.
import { useEffect, useState, type ReactNode } from "react";

import { Card, Field, Segmented, inputClass } from "../../components/ui";
import { PAGE_SECTIONS } from "../../lib/pages";
import { arrangeNav } from "../organize/tree";
import {
  ACCENTS,
  START_PAGE_LABELS,
  TEXT_SIZE_LABELS,
  THEME_LABELS,
  type Accent,
  type Look,
  type StartPage,
} from "../../lib/theme";

/** A titled row of buttons (not a <label>, which would click the first button). */
function Group({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{label}</p>
      {children}
      {hint && <p className="text-xs text-zinc-500 dark:text-zinc-400">{hint}</p>}
    </div>
  );
}

export default function AppearanceSettings({ look, onChange }: { look: Look; onChange: (change: Partial<Look>) => void }) {
  // The name is saved a moment after typing stops, not on every letter.
  const [name, setName] = useState(look.name);
  useEffect(() => setName(look.name), [look.name]);
  useEffect(() => {
    if (name === look.name) return;
    const timer = window.setTimeout(() => onChange({ name: name.slice(0, 40) }), 500);
    return () => window.clearTimeout(timer);
  }, [name, look.name, onChange]);

  return (
    <Card>
      <h2 className="mb-1 text-lg font-medium">Appearance</h2>
      <p className="mb-5 text-sm text-zinc-500 dark:text-zinc-400">
        Make Keptwise yours. Ctrl+Shift+L switches light and dark from anywhere.
      </p>
      <div className="space-y-5">
        <Group label="Theme">
          <Segmented
            label="Theme"
            value={look.theme}
            onChange={(theme) => onChange({ theme })}
            options={(["light", "dark", "system"] as const).map((value) => ({ value, label: THEME_LABELS[value] }))}
          />
        </Group>

        <Group label="Accent colour" hint="Used for buttons, links and the page you're on. Default has no colour: dark in light mode, light in dark mode.">
          <AccentSwatches value={look.accent} onChange={(accent) => onChange({ accent })} />
        </Group>

        <Group label="Text size">
          <Segmented
            label="Text size"
            value={look.text_size}
            onChange={(text_size) => onChange({ text_size })}
            options={(["small", "normal", "large"] as const).map((value) => ({ value, label: TEXT_SIZE_LABELS[value] }))}
          />
        </Group>

        <Field label="Open Keptwise on">
          <select
            value={look.start_page}
            onChange={(event) => onChange({ start_page: event.target.value as StartPage })}
            className={`${inputClass} block max-w-xs`}
          >
            {(Object.keys(START_PAGE_LABELS) as StartPage[]).map((page) => (
              <option key={page} value={page}>
                {START_PAGE_LABELS[page]}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Your name" hint="Used to greet you at the top of the Library. Leave it empty for no greeting.">
          <input
            type="text"
            value={name}
            maxLength={40}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Sam"
            className={`${inputClass} block max-w-xs`}
          />
        </Field>

        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={look.compact_sidebar}
            onChange={(event) => onChange({ compact_sidebar: event.target.checked })}
            className="h-4 w-4 accent-indigo-600"
          />
          <span>
            <span className="font-medium">Slim sidebar</span>
            <span className="block text-zinc-500 dark:text-zinc-400">Show only the icons, for more room.</span>
          </span>
        </label>

        <Group label="Library pictures">
          <Segmented
            label="Library picture size"
            value={look.card_size}
            onChange={(card_size) => onChange({ card_size })}
            options={[
              { value: "small", label: "Smaller" },
              { value: "medium", label: "Normal" },
              { value: "large", label: "Bigger" },
            ]}
          />
        </Group>

        <label className="flex cursor-pointer items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={look.card_actions}
            onChange={(event) => onChange({ card_actions: event.target.checked })}
            className="h-4 w-4 accent-indigo-600"
          />
          <span>
            <span className="font-medium">Quick buttons on saves</span>
            <span className="block text-zinc-500 dark:text-zinc-400">
              Point at a save in the Library to tag it, file it, add it to a plan or unsave it.
            </span>
          </span>
        </label>

        <SidebarChoices look={look} onChange={onChange} />

        <Group label="Tips" hint="Tips and suggestions you closed stay closed.">
          <button
            type="button"
            disabled={look.dismissed_tips.length === 0}
            onClick={() => onChange({ dismissed_tips: [] })}
            className="text-sm text-indigo-600 hover:underline disabled:text-zinc-400 disabled:no-underline dark:text-indigo-400"
          >
            {look.dismissed_tips.length === 0
              ? "No tips closed"
              : `Show the ${look.dismissed_tips.length} closed tip${look.dismissed_tips.length === 1 ? "" : "s"} again`}
          </button>
        </Group>
      </div>
    </Card>
  );
}

/** Which pages the sidebar shows and in what order, per section (dragging
 * them in the sidebar does the same). */
function SidebarChoices({ look, onChange }: { look: Look; onChange: (change: Partial<Look>) => void }) {
  const sections = PAGE_SECTIONS.map((section) => ({ ...section, pages: arrangeNav(section.pages, look.nav_order, []) }));
  const allPaths = () => sections.flatMap((section) => section.pages.map((page) => page.path));
  const move = (path: string, by: number) => {
    const next = allPaths();
    const index = next.indexOf(path);
    const [page] = next.splice(index, 1);
    next.splice(index + by, 0, page);
    onChange({ nav_order: next });
  };
  const toggleHidden = (path: string, hide: boolean) =>
    onChange({ nav_hidden: hide ? [...look.nav_hidden, path] : look.nav_hidden.filter((p) => p !== path) });

  return (
    <Group label="Sidebar">
      <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
        Hold a page in the sidebar and drag it to move it within its section, or use the arrows here. Untick a page to hide it.
      </p>
      <div className="grid max-w-xl gap-3 sm:grid-cols-2">
        {sections.map((section) => (
          <div key={section.id}>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-zinc-400">{section.title}</p>
            <ul className="divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
              {section.pages.map((page, index) => (
                <li key={page.path} className="flex items-center gap-2 px-3 py-1.5 text-sm">
                  <input
                    type="checkbox"
                    aria-label={`Show ${page.label}`}
                    checked={page.path === "/settings" || !look.nav_hidden.includes(page.path)}
                    disabled={page.path === "/settings"}
                    onChange={(event) => toggleHidden(page.path, !event.target.checked)}
                    className="h-4 w-4 accent-indigo-600"
                  />
                  <span className="flex-1">{page.label}</span>
                  <button type="button" aria-label={`Move ${page.label} up`} disabled={index === 0} onClick={() => move(page.path, -1)} className="rounded px-1.5 text-zinc-500 hover:bg-zinc-100 disabled:opacity-30 dark:hover:bg-zinc-800">
                    ↑
                  </button>
                  <button type="button" aria-label={`Move ${page.label} down`} disabled={index === section.pages.length - 1} onClick={() => move(page.path, 1)} className="rounded px-1.5 text-zinc-500 hover:bg-zinc-100 disabled:opacity-30 dark:hover:bg-zinc-800">
                    ↓
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      {(look.nav_order.length > 0 || look.nav_hidden.length > 0) && (
        <button type="button" className="mt-2 text-xs text-indigo-600 hover:underline dark:text-indigo-400" onClick={() => onChange({ nav_order: [], nav_hidden: [] })}>
          Back to the standard order
        </button>
      )}
    </Group>
  );
}

/** The accent colours as round swatches (also used by the first-run setup). */
export function AccentSwatches({ value, onChange }: { value: Accent; onChange: (accent: Accent) => void }) {
  return (
    <div role="radiogroup" aria-label="Accent colour" className="flex flex-wrap gap-2">
      {ACCENTS.map((accent) => {
        const chosen = value === accent.value;
        return (
          <button
            key={accent.value}
            type="button"
            role="radio"
            aria-checked={chosen}
            aria-label={accent.label}
            title={accent.label}
            onClick={() => onChange(accent.value)}
            className={`flex h-9 w-9 items-center justify-center rounded-full ring-offset-2 ring-offset-white transition dark:ring-offset-zinc-900 ${
              chosen ? "ring-2 ring-zinc-900 dark:ring-white" : "hover:scale-110"
            } ${accent.swatch ? "" : "bg-zinc-900 dark:bg-zinc-100"}`}
            style={accent.swatch ? { backgroundColor: accent.swatch } : undefined}
          >
            {chosen && (
              <svg viewBox="0 0 16 16" className={`h-4 w-4 ${accent.swatch ? "text-white" : "text-white dark:text-zinc-900"}`} fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                <path d="M3.5 8.5l3 3 6-7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </button>
        );
      })}
    </div>
  );
}
