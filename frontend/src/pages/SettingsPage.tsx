// Settings (#/settings, #/settings?section=ai): a search box and a list of
// sections on the left; click one to jump there. Typing in the search box
// shows only the sections with a matching setting, and says which settings
// matched. Everything is saved on this computer, straight away.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { icons } from "../components/icons";
import { Card, Notice } from "../components/ui";
import type { AiOverview } from "../features/ai/aiApi";
import AiSettings from "../features/ai/AiSettings";
import SpeechSettings from "../features/enrich/SpeechSettings";
import AppearanceSettings from "../features/look/AppearanceSettings";
import SortingSettings from "../features/sorting/SortingSettings";
import StorageSettings from "../features/storage/StorageSettings";
import type { UpdateStatus } from "../features/updates/updatesApi";
import UpdatesSettings from "../features/updates/UpdatesSettings";
import { useRoute } from "../lib/router";
import type { Look } from "../lib/theme";

type Section = {
  id: string;
  title: string;
  blurb: string;
  // The names of the settings inside, for the search box.
  settings: string[];
  extra?: string[]; // other words people might type
  render: () => ReactNode;
};

function matches(section: Section, words: string[]): string[] {
  if (words.length === 0) return [];
  const hay = (text: string) => text.toLowerCase();
  const all = (text: string) => words.every((w) => hay(text).includes(w));
  const found = section.settings.filter(all);
  if (found.length) return found;
  if (all([section.title, section.blurb, ...section.settings, ...(section.extra ?? [])].join(" "))) return ["(this section)"];
  return [];
}

export default function SettingsPage({
  overview,
  onAiChange,
  extraSections,
  look,
  onLookChange,
  updates,
  onUpdatesChange,
}: {
  overview: AiOverview | null;
  onAiChange: (overview: AiOverview) => void;
  extraSections?: ReactNode;
  look?: Look;
  onLookChange?: (change: Partial<Look>) => void;
  updates?: UpdateStatus | null;
  onUpdatesChange?: (status: UpdateStatus) => void;
}) {
  const route = useRoute();
  const [query, setQuery] = useState("");
  const [current, setCurrent] = useState<string>("ai");
  const scroller = useRef<HTMLDivElement>(null);

  const sections: Section[] = useMemo(() => {
    const list: Section[] = [
      {
        id: "ai",
        title: "AI",
        blurb: "Which AI writes notes, sorts, tags and answers the Assistant.",
        settings: ["AI provider", "Local AI (Ollama, LM Studio)", "Cloud AI (Claude, OpenAI, Gemini)", "API key", "Model", "Download a model", "Test the connection"],
        extra: ["gemma", "ollama", "key", "claude", "openai", "local", "cloud"],
        render: () => (
          <Card>
            <h2 className="mb-1 text-lg font-medium">AI</h2>
            <p className="mb-5 text-sm text-zinc-500 dark:text-zinc-400">
              The AI writes the notes and steps for each saved video, sorts and tags them, and answers in the AI Assistant.
            </p>
            {overview ? <AiSettings overview={overview} onChange={onAiChange} /> : <Notice>Loading AI settings…</Notice>}
          </Card>
        ),
      },
    ];
    if (look && onLookChange) {
      list.push({
        id: "appearance",
        title: "Appearance",
        blurb: "Theme, colours, text size, sidebar and cards.",
        settings: ["Theme", "Dark mode", "Light mode", "Accent colour", "Text size", "Open Keptwise on", "Your name", "Slim sidebar", "Library pictures", "Quick buttons on saves", "Sidebar pages and order", "Tips"],
        extra: ["colour", "color", "font", "start page", "hide page", "reorder"],
        render: () => <AppearanceSettings look={look} onChange={onLookChange} />,
      });
    }
    list.push(
      {
        id: "sorting",
        title: "Notes",
        blurb: "What the AI writes for each save. Sorting and tagging are chosen on the Collections and Tags pages.",
        settings: [
          "Look at the video's pictures",
          "What each kind of video turns into",
          "Safe to unsave on the platform",
        ],
        extra: ["unsave", "steps", "recipe", "kind", "notes", "pictures", "vision", "images"],
        render: () => <SortingSettings />,
      },
      {
        id: "speech",
        title: "Transcripts",
        blurb: "Speech to text for your videos.",
        settings: ["Speech model", "Language", "Use the graphics card", "Download the speech model"],
        extra: ["whisper", "transcribe", "gpu", "speech", "audio"],
        render: () => <SpeechSettings />,
      },
      {
        id: "storage",
        title: "Storage",
        blurb: "Where your data lives and how much room it takes.",
        settings: ["Data folder", "Space used", "Free up space", "Open the data folder"],
        extra: ["disk", "folder", "delete", "backup", "space", "files"],
        render: () => <StorageSettings />,
      },
    );
    if (onUpdatesChange) {
      list.push({
        id: "updates",
        title: "Updates",
        blurb: "New versions of Keptwise.",
        settings: ["Check for a new version once a day", "Check now"],
        extra: ["version", "github", "update", "release"],
        render: () => <UpdatesSettings status={updates ?? null} onChange={onUpdatesChange} />,
      });
    }
    return list;
  }, [overview, onAiChange, look, onLookChange, updates, onUpdatesChange]);

  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const hits = new Map(sections.map((s) => [s.id, matches(s, words)]));
  const shown = words.length ? sections.filter((s) => (hits.get(s.id) ?? []).length > 0) : sections;

  function jump(id: string) {
    setCurrent(id);
    document.getElementById(`settings-${id}`)?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  // ?section=ai (from the sidebar corner or other screens) jumps there.
  const wanted = route.query.get("section");
  useEffect(() => {
    if (wanted && sections.some((s) => s.id === wanted)) {
      setCurrent(wanted);
      window.setTimeout(() => document.getElementById(`settings-${wanted}`)?.scrollIntoView?.({ block: "start" }), 50);
    }
  }, [wanted, sections]);

  // Which section is on screen: the nav follows while scrolling.
  useEffect(() => {
    const main = document.querySelector("main");
    if (!main || typeof IntersectionObserver === "undefined") return;
    const seen = new IntersectionObserver(
      (entries) => {
        const top = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0];
        if (top) setCurrent(top.target.id.replace("settings-", ""));
      },
      { root: main, rootMargin: "0px 0px -70% 0px" },
    );
    for (const section of shown) {
      const element = document.getElementById(`settings-${section.id}`);
      if (element) seen.observe(element);
    }
    return () => seen.disconnect();
  }, [shown.map((s) => s.id).join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div ref={scroller} className="mx-auto flex max-w-5xl gap-8 px-8 py-8">
      <aside className="sticky top-0 hidden w-48 shrink-0 self-start pt-24 md:block" aria-label="Settings sections">
        <nav className="space-y-0.5">
          {sections.map((section) => {
            const found = hits.get(section.id) ?? [];
            const dim = words.length > 0 && found.length === 0;
            return (
              <button
                key={section.id}
                type="button"
                onClick={() => jump(section.id)}
                aria-current={current === section.id ? "true" : undefined}
                disabled={dim}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-1.5 text-left text-sm transition ${
                  current === section.id && !dim
                    ? "bg-indigo-50 font-medium text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300"
                    : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
                } ${dim ? "opacity-40" : ""}`}
              >
                {section.title}
                {words.length > 0 && found.length > 0 && found[0] !== "(this section)" && (
                  <span className="rounded-full bg-indigo-600 px-1.5 text-[10px] text-white">{found.length}</span>
                )}
              </button>
            );
          })}
        </nav>
        <p className="mt-6 px-3 text-xs text-zinc-400">Everything is saved on this computer, straight away.</p>
      </aside>

      <div className="min-w-0 flex-1 space-y-6">
        <header>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Find a setting by name, or pick a section.</p>
          <div className="mt-3 max-w-md">
            <SearchBox query={query} onChange={setQuery} />
          </div>
        </header>
        {words.length > 0 && (
          <div className="rounded-xl bg-zinc-100 px-4 py-3 text-sm dark:bg-zinc-800/70" role="status">
            {shown.length === 0 ? (
              <>No setting matches “{query.trim()}”. Try another word, like “dark”, “key” or “tags”.</>
            ) : (
              <ul className="space-y-1">
                {shown.map((section) => (
                  <li key={section.id}>
                    <button type="button" className="font-medium text-indigo-700 hover:underline dark:text-indigo-300" onClick={() => jump(section.id)}>
                      {section.title}
                    </button>
                    {(hits.get(section.id) ?? [])[0] !== "(this section)" && (
                      <span className="text-zinc-600 dark:text-zinc-400">: {(hits.get(section.id) ?? []).join(", ")}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {shown.map((section) => (
          <section key={section.id} id={`settings-${section.id}`} className="scroll-mt-4" aria-label={section.title}>
            {section.render()}
          </section>
        ))}
        {words.length === 0 && extraSections}
      </div>
    </div>
  );
}

function SearchBox({ query, onChange }: { query: string; onChange: (value: string) => void }) {
  return (
    <label className="relative block">
      <span className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400">{icons.search}</span>
      <input
        type="search"
        value={query}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Find a setting"
        aria-label="Find a setting"
        className="w-full rounded-lg border border-zinc-300 bg-white py-1.5 pl-8 pr-2.5 text-sm placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-zinc-700 dark:bg-zinc-900"
      />
    </label>
  );
}
