// The AI's choices. How it picks collections and tags lives on the Sort page
// (where everything the AI does happens); what the notes contain is a
// Settings section.
import { useEffect, useState, type ReactNode } from "react";

import { Button, Card, Notice, Segmented, inputClass } from "../../components/ui";
import { errorText } from "../../lib/api";
import { navigate } from "../../lib/router";
import {
  sortingApi,
  type Collection,
  type Rule,
  type SortingSettings as Settings,
  type SortingSettingsResponse,
} from "./sortingApi";

// review_below for each choice (the AI's words score clear 0.95, likely 0.75, maybe 0.5, guess 0.25).
const REVIEW_CHOICES = [
  { value: "clear", label: "Clear only", below: 0.9 },
  { value: "likely", label: "Clear or likely (recommended)", below: 0.6 },
  { value: "maybe", label: "Anything but a guess", below: 0.4 },
] as const;

function reviewChoice(below: number): (typeof REVIEW_CHOICES)[number]["value"] {
  if (below >= 0.8) return "clear";
  return below >= 0.55 ? "likely" : "maybe";
}

/** Loading and saving the AI's choices (shared by Settings and the pages that show them). */
export function useSortingSettings() {
  const [data, setData] = useState<SortingSettingsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    sortingApi.getSettings().then(setData).catch((e) => setError(errorText(e)));
  }, []);

  async function save(changes: Partial<Settings>) {
    if (!data) return;
    const next = { ...data.settings, ...changes };
    setData({ ...data, settings: next });
    setError(null);
    try {
      setData(await sortingApi.saveSettings(next));
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
    } catch (e) {
      setError(errorText(e));
    }
  }
  return { data, error, saved, save };
}

/**
 * How the AI picks collections: your rules, how many per save, and how sure
 * it must be to file by itself. On the Sort page, under "Options".
 */
export function CollectionSortOptions({ collections }: { collections: Collection[] }) {
  const { data, error, saved, save } = useSortingSettings();
  if (!data) return error ? <Notice tone="error">{error}</Notice> : <p className="text-sm text-zinc-500">Loading…</p>;
  const settings = data.settings;
  return (
    <div className="space-y-5">
      {error && <Notice tone="error">{error}</Notice>}
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        The AI only ever picks from your own collections; it never makes new ones.
      </p>
      <Setting label="Collections per save" help="With more than one, extra collections are only added when the AI is very sure. (You can put a save in up to 10 yourself.)">
        <Segmented
          label="Collections per save"
          value={String(settings.max_collections) as "1" | "2" | "3"}
          options={[
            { value: "1", label: "Just one" },
            { value: "2", label: "Up to 2" },
            { value: "3", label: "Up to 3" },
          ]}
          onChange={(value) => save({ max_collections: Number(value) })}
        />
      </Setting>
      <Setting
        label="With “Put into collections automatically” on, file a save when the fit is"
        help="The AI rates each fit as clear, likely, maybe or a guess. Anything below your choice waits in Unsorted with its suggestion."
      >
        <Segmented
          label="File by itself when the fit is"
          value={reviewChoice(settings.review_below)}
          options={REVIEW_CHOICES.map(({ value, label }) => ({ value, label }))}
          onChange={(value) => save({ review_below: REVIEW_CHOICES.find((c) => c.value === value)?.below ?? 0.6 })}
        />
      </Setting>
      <Setting
        label="Platform collection names as a hint"
        help="The AI can read the name of the TikTok, Instagram, YouTube or Facebook collection a save was in."
      >
        <Segmented
          label="Platform collections"
          value={settings.platform_collections}
          options={[
            { value: "hint", label: "Use as a hint" },
            { value: "ignore", label: "Ignore them" },
          ]}
          onChange={(value) => save({ platform_collections: value })}
        />
      </Setting>
      <RulesEditor rules={settings.rules} names={collections.map((c) => c.name)} onChange={(rules) => save({ rules })} />
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        To keep the AI out of one collection, right-click it and untick “The AI can sort saves into it”.{" "}
        {saved && <span className="text-emerald-600 dark:text-emerald-400">Saved.</span>}
      </p>
    </div>
  );
}

/** How the AI tags saves. On the Sort page, under "Options". */
export function TagOptions() {
  const { data, error, saved, save } = useSortingSettings();
  if (!data) return error ? <Notice tone="error">{error}</Notice> : <p className="text-sm text-zinc-500">Loading…</p>;
  return (
    <div className="space-y-5">
      {error && <Notice tone="error">{error}</Notice>}
      <TagSettings settings={data.settings} onSave={save} />
      {saved && <p className="text-xs text-emerald-600 dark:text-emerald-400">Saved.</p>}
    </div>
  );
}

/** One on/off choice of the AI's, as a switch: [is it on (null while loading), change it]. */
export function useAiSwitch(key: "auto_tag" | "auto_sort" | "auto_notes" | "look_at_pictures", fallback = true): [boolean | null, (on: boolean) => void] {
  const { data, save } = useSortingSettings();
  return [data ? (data.settings[key] ?? fallback) : null, (on) => void save({ [key]: on })];
}

export default function SortingSettings() {
  const { data, error, saved, save } = useSortingSettings();

  if (!data) {
    return (
      <Card>
        <h2 className="text-lg font-medium">Notes</h2>
        <div className="mt-3">{error ? <Notice tone="error">{error}</Notice> : <Notice>Loading…</Notice>}</div>
      </Card>
    );
  }
  const settings = data.settings;

  return (
    <Card>
      <div className="mb-1 flex items-center justify-between gap-3">
        <h2 className="text-lg font-medium">Notes</h2>
        {saved && <span className="text-xs text-emerald-600 dark:text-emerald-400">Saved</span>}
      </div>
      <p className="kw-tip mb-5 text-sm text-zinc-500 dark:text-zinc-400">
        What the AI writes for each save. How it picks collections and tags, and starting it, is on the{" "}
        <button type="button" className="underline" onClick={() => navigate("/transcripts")}>
          Sort
        </button>{" "}
        page.
      </p>
      {error && (
        <div className="mb-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}

      <div className="space-y-6">
        <Setting
          label="Look at the video's pictures"
          help="The AI also sees a few stills from each video (or its cover picture), so it can read text on the screen and recognise the place, dish or product. It needs a model that can see; one that can't is noticed and the pictures are left out."
        >
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              role="switch"
              className="h-4 w-4 accent-indigo-600"
              checked={settings.look_at_pictures !== false}
              onChange={(e) => save({ look_at_pictures: e.target.checked })}
            />
            Use pictures as well as the caption and transcript
          </label>
        </Setting>

        <Setting label="What each kind of video turns into" help="The AI follows these when it writes the key details and next steps.">
          <div className="space-y-2">
            {data.kinds.map((kind) => (
              <details key={kind.id} className="rounded-xl border border-zinc-200 px-3 py-2 dark:border-zinc-800">
                <summary className="cursor-pointer text-sm font-medium">{kind.label}</summary>
                <textarea
                  className={`${inputClass} mt-2 min-h-20`}
                  aria-label={`What a ${kind.label.toLowerCase()} video turns into`}
                  defaultValue={settings.kind_steps[kind.id] ?? kind.default}
                  maxLength={600}
                  onBlur={(event) => {
                    if (event.target.value.trim() !== settings.kind_steps[kind.id]) {
                      save({ kind_steps: { ...settings.kind_steps, [kind.id]: event.target.value } });
                    }
                  }}
                />
                {settings.kind_steps[kind.id] !== kind.default && (
                  <button
                    type="button"
                    className="mt-1 text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                    onClick={() => save({ kind_steps: { ...settings.kind_steps, [kind.id]: kind.default } })}
                  >
                    Back to the suggested text
                  </button>
                )}
              </details>
            ))}
          </div>
        </Setting>
      </div>
    </Card>
  );
}

function Setting({ label, help, children }: { label: string; help?: ReactNode; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <span className="block text-sm font-medium text-zinc-800 dark:text-zinc-200">{label}</span>
      {children}
      {help && <span className="kw-tip block text-xs text-zinc-500 dark:text-zinc-400">{help}</span>}
    </div>
  );
}

function RulesEditor({ rules, names, onChange }: { rules: Rule[]; names: string[]; onChange: (rules: Rule[]) => void }) {
  const [draft, setDraft] = useState<Rule>({ field: "author", value: "", collection: names[0] ?? "" });
  const [target, setTarget] = useState<"collection" | "tag">("collection");
  const goal = target === "collection" ? draft.collection : draft.tag ?? "";
  const ready = draft.value.trim() !== "" && goal.trim() !== "";
  return (
    <Setting label="Your rules" help="Checked before the AI. A rule's tag is made if it doesn't exist yet; its collection must be one of yours.">
      {rules.length > 0 && (
        <ul className="space-y-1.5">
          {rules.map((rule, index) => (
            <li key={`${rule.field}-${rule.value}-${rule.collection}`} className="flex items-center gap-2 text-sm">
              <span className="flex-1 rounded-lg bg-zinc-100 px-3 py-1.5 dark:bg-zinc-800">
                {rule.field === "author" ? <>Anything from <b>@{rule.value.replace(/^@/, "")}</b></> : <>Anything mentioning <b>{rule.value}</b></>}{" "}
                {rule.collection && (
                  <>
                    goes to <b>{rule.collection}</b>
                  </>
                )}
                {rule.collection && rule.tag ? " and " : " "}
                {rule.tag && (
                  <>
                    gets the tag <b>#{rule.tag}</b>
                  </>
                )}
              </span>
              <Button size="sm" variant="ghost" aria-label={`Delete rule ${index + 1}`} onClick={() => onChange(rules.filter((_, i) => i !== index))}>
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!ready) return;
          onChange([
            ...rules,
            target === "collection"
              ? { field: draft.field, value: draft.value.trim(), collection: draft.collection.trim(), tag: "" }
              : { field: draft.field, value: draft.value.trim(), collection: "", tag: (draft.tag ?? "").trim().replace(/^#/, "") },
          ]);
          setDraft({ ...draft, value: "" });
        }}
      >
        <select
          className={`${inputClass} w-auto`}
          aria-label="Rule type"
          value={draft.field}
          onChange={(event) => setDraft({ ...draft, field: event.target.value as Rule["field"] })}
        >
          <option value="author">Anything from creator</option>
          <option value="text">Anything mentioning</option>
        </select>
        <div className="min-w-32 flex-1">
          <input
            className={inputClass}
            aria-label={draft.field === "author" ? "Creator name" : "Word or phrase"}
            placeholder={draft.field === "author" ? "@creator" : "Japan"}
            value={draft.value}
            onChange={(event) => setDraft({ ...draft, value: event.target.value })}
          />
        </div>
        <select
          className={`${inputClass} w-auto`}
          aria-label="What the rule does"
          value={target}
          onChange={(event) => setTarget(event.target.value as "collection" | "tag")}
        >
          <option value="collection">goes to</option>
          <option value="tag">gets the tag</option>
        </select>
        <div className="min-w-32 flex-1">
          {target === "collection" ? (
            <input
              className={inputClass}
              aria-label="Collection for this rule"
              list="rule-collections"
              placeholder="Collection"
              value={draft.collection}
              onChange={(event) => setDraft({ ...draft, collection: event.target.value })}
            />
          ) : (
            <input
              className={inputClass}
              aria-label="Tag for this rule"
              placeholder="tag"
              maxLength={40}
              value={draft.tag ?? ""}
              onChange={(event) => setDraft({ ...draft, tag: event.target.value })}
            />
          )}
          <datalist id="rule-collections">
            {names.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        </div>
        <Button type="submit" variant="secondary" disabled={!ready}>
          Add rule
        </Button>
      </form>
    </Setting>
  );
}

const TAG_COUNTS = [0, 3, 5, 6, 8, 10];

function TagSettings({ settings, onSave }: { settings: Settings; onSave: (changes: Partial<Settings>) => void }) {
  const [mine, setMine] = useState((settings.my_tags ?? []).join(", "));
  useEffect(() => setMine((settings.my_tags ?? []).join(", ")), [settings.my_tags]);

  const saveMine = () => {
    const tags = mine.split(",").map((t) => t.trim().replace(/^#/, "").toLowerCase()).filter(Boolean);
    if (tags.join(",") !== (settings.my_tags ?? []).join(",")) onSave({ my_tags: tags });
  };

  return (
    <>
      <Setting label="Tags per save" help="How many tags the AI gives each save. They're broad, common words (like “pasta” or “london”). A save holds up to 10 tags in all, yours included.">
        <Segmented
          label="Tags per video"
          value={String(TAG_COUNTS.includes(settings.tags_per_video) ? settings.tags_per_video : 6)}
          options={TAG_COUNTS.map((n) => ({ value: String(n), label: n === 0 ? "None" : `Up to ${n}` }))}
          onChange={(value) => onSave({ tags_per_video: Number(value) })}
        />
      </Setting>

      <Setting
        label="Which tags the AI uses"
        help={
          settings.tag_mode === "free"
            ? "The AI reuses tags you already have, then the video's own hashtags, then a built-in list of common tags, before it makes a new word."
            : settings.tag_mode === "prefer_mine"
              ? "The AI uses your tags when they fit, and adds its own words when they don't."
              : "The AI only uses tags from your list."
        }
      >
        <Segmented
          label="Which tags the AI uses"
          value={settings.tag_mode}
          options={[
            { value: "free", label: "Any words" },
            { value: "prefer_mine", label: "Mine first" },
            { value: "only_mine", label: "Only mine" },
          ]}
          onChange={(value) => onSave({ tag_mode: value })}
        />
        {settings.tag_mode !== "free" && (
          <input
            className={`${inputClass} mt-2`}
            aria-label="Your tags"
            placeholder="pasta, gym, japan trip, gift ideas"
            value={mine}
            onChange={(e) => setMine(e.target.value)}
            onBlur={saveMine}
          />
        )}
      </Setting>

    </>
  );
}
