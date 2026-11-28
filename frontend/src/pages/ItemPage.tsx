// One save on its own page (#/item/12): picture, AI notes, next steps as a
// checklist, key details, collections and the transcript.
// Keys: 1-9 tick a step, O opens the video, Esc goes back.
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { icons } from "../components/icons";
import { Badge, Button, Card, Notice } from "../components/ui";
import { enrichApi, formatDuration } from "../features/enrich/enrichApi";
import { PlanPanel } from "../features/library/QuickActions";
import StepsChecklist from "../features/library/StepsChecklist";
import Thumb from "../features/library/Thumb";
import { displayTitle, formatDate, libraryApi, type ItemPage as Details, type LibraryItem } from "../features/library/libraryApi";
import { announceChange } from "../features/organize/organizeApi";
import CollectionPicker from "../features/organize/CollectionPicker";
import TagEditor from "../features/organize/TagEditor";
import { TagIdeas, suggestionOf } from "../features/sorting/Unsorted";
import { sortingApi, type Collection, type ItemCard, type Space } from "../features/sorting/sortingApi";
import { errorText } from "../lib/api";
import { navigate } from "../lib/router";

function typing(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null;
  return !!element && (element.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(element.tagName));
}

function goBack() {
  if (window.history.length > 1) window.history.back();
  else navigate("/library");
}

function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{title}</h2>
        {aside}
      </div>
      {children}
    </Card>
  );
}

function NoNotesYet({ item }: { item: LibraryItem }) {
  if (item.gone) {
    return (
      <Notice tone="warning">
        This video is marked unavailable on {item.platform_name}. Your saved details are still here.
      </Notice>
    );
  }
  if (item.status === "failed") {
    return <Notice tone="error">This video couldn't be read{item.error ? `: ${item.error}` : "."}</Notice>;
  }
  const transcribed = item.status === "enriched";
  return (
    <Notice>
      <b>Needs notes.</b>{" "}
      {transcribed ? "The transcript is ready; " : "It hasn't been transcribed yet; "}
      <a className="font-medium underline" href="#/transcripts">
        {transcribed ? "write its notes on the Sort page" : "get its transcript on the Sort page"}
      </a>
      .
    </Notice>
  );
}

export default function ItemPage({ itemId }: { itemId: number }) {
  const [details, setDetails] = useState<Details | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [spaces, setSpaces] = useState<Space[]>([]);

  useEffect(() => {
    setDetails(null);
    setError(null);
    libraryApi.item(itemId).then(setDetails).catch((e) => setError(errorText(e)));
    sortingApi
      .collections()
      .then((o) => {
        setCollections(o.collections);
        setSpaces(o.spaces ?? []);
      })
      .catch(() => undefined);
  }, [itemId]);

  /** Tags or collections changed: keep the save's progress fields, take the rest. */
  const mergeCard = useCallback((card: ItemCard) => {
    setDetails((old) => (old ? { ...old, item: { ...old.item, ...card } } : old));
  }, []);

  const changeCollections = useCallback(
    async (change: () => Promise<ItemCard>) => {
      setError(null);
      try {
        mergeCard(await change());
        announceChange();
      } catch (e) {
        setError(errorText(e));
      }
    },
    [mergeCard],
  );

  const item = details?.item ?? null;

  const update = useCallback(
    async (change: () => Promise<LibraryItem>) => {
      setBusy(true);
      setError(null);
      try {
        const next = await change();
        setDetails((old) => (old ? { ...old, item: next } : old));
      } catch (e) {
        setError(errorText(e));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  const toggleStep = useCallback(
    (index: number, done: boolean) => void update(() => libraryApi.tick(itemId, index, done)),
    [itemId, update],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (typing(event.target) || event.ctrlKey || event.altKey || event.metaKey) return;
      if (document.querySelector('[role="dialog"]')) return; // a dialog is open on top
      if (event.key === "Escape") {
        goBack();
      } else if (item && /^[1-9]$/.test(event.key)) {
        const index = Number(event.key) - 1;
        if (index < item.steps.length && !busy) toggleStep(index, !item.steps_checked[index]);
      } else if (item && event.key.toLowerCase() === "o") {
        window.open(item.url, "_blank", "noopener");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, busy, toggleStep]);

  if (!item) {
    return (
      <div className="mx-auto max-w-5xl px-8 py-8">
        <Button variant="ghost" size="sm" onClick={goBack}>
          <span className="h-4 w-4">{icons.back}</span> Back
        </Button>
        <div className="mt-4">{error ? <Notice tone="error">{error}</Notice> : <Notice>Loading…</Notice>}</div>
      </div>
    );
  }

  const meta = [
    item.author ? `@${item.author.replace(/^@/, "")}` : null,
    formatDuration(item.duration_s),
    item.saved_at ? `saved ${formatDate(item.saved_at)}` : null,
  ].filter(Boolean);
  const hasNotes = item.status === "processed";
  const retryTarget = item.gone ? "unavailable" : item.no_sound ? "no_speech"
    : item.error && item.status === "imported" ? "waiting"
      : item.status === "failed" || item.error?.startsWith("Got the details,") ? "failed" : null;

  async function retryTranscript() {
    if (!retryTarget) return;
    setBusy(true);
    setError(null);
    try {
      await enrichApi.start(1, retryTarget, itemId);
      navigate("/sort");
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }
  const idea = item.collections.length === 0 ? suggestionOf(item, collections) : null;
  const started = item.steps_checked.some(Boolean);

  return (
    <div className="mx-auto max-w-5xl px-8 py-8">
      <Button variant="ghost" size="sm" onClick={goBack}>
        <span className="h-4 w-4">{icons.back}</span> Back
      </Button>

      <div className="mt-4 flex flex-col gap-6 md:flex-row">
        <Thumb item={item} className="aspect-[4/5] w-full shrink-0 rounded-2xl md:w-56" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge>{item.platform_name}</Badge>
            {item.kind_label && <Badge tone="indigo">{item.kind_label}</Badge>}
            {!hasNotes && !item.gone && item.status !== "failed" && <Badge tone="amber">Needs notes</Badge>}
            {item.no_sound && <Badge>No speech detected</Badge>}
            {item.gone && <Badge tone="red">Unavailable</Badge>}
            {item.unsaved && <Badge>Unsaved on {item.platform_name}</Badge>}
          </div>
          <h1 className="mt-2 line-clamp-3 break-words text-2xl font-semibold leading-tight tracking-tight" title={displayTitle(item)}>
            {displayTitle(item)}
          </h1>
          {meta.length > 0 && <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{meta.join(" · ")}</p>}
          {item.summary && <p className="mt-4 leading-relaxed text-zinc-700 dark:text-zinc-300">{item.summary}</p>}

          <div className="mt-5 flex flex-wrap gap-2">
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-zinc-300 bg-white px-3.5 py-2 text-sm font-medium text-zinc-800 transition hover:bg-zinc-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800"
            >
              <span className="h-4 w-4">{icons.external}</span> Open on {item.platform_name}
            </a>
            <Button variant="ghost" onClick={() => navigate(`/chat?items=${itemId}`)} title="Ask the AI Assistant about this save">
              <span className="h-4 w-4">{icons.chat}</span>
              Ask AI
            </Button>
            {!item.deleted && !item.gone && (item.status === "failed" || item.error) && (
              <Button variant="ghost" disabled={busy} onClick={() => void update(() => libraryApi.patch(itemId, { unavailable: true }))}>
                Mark unavailable
              </Button>
            )}
            {!item.deleted && retryTarget && (
              <Button variant="secondary" disabled={busy} onClick={() => void retryTranscript()}>
                {item.gone ? "Check availability" : "Retry transcript"}
              </Button>
            )}
            {!item.deleted && (
              <Button
                variant="ghost"
                disabled={busy}
                title="Move this save to the Keptwise Archive, where you can put it back"
                onClick={() => void update(() => libraryApi.patch(itemId, { deleted: true }))}
              >
                <span className="h-4 w-4">{icons.archive}</span>
                Archive
              </Button>
            )}
          </div>
        </div>
      </div>

      {item.deleted && (
        <div className="mt-4">
          <Notice tone="warning">
            This save is archived in Keptwise.{" "}
            <button type="button" className="font-medium underline" disabled={busy} onClick={() => void update(() => libraryApi.patch(itemId, { deleted: false }))}>
              Put it back
            </button>
          </Notice>
        </div>
      )}

      {error && (
        <div className="mt-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="space-y-6">
          {!hasNotes && <NoNotesYet item={item} />}
          {item.steps.length > 0 && (
            <Section
              title="Next steps"
              aside={
                started && (
                  <Button variant="ghost" size="sm" disabled={busy} onClick={() => void update(() => libraryApi.restart(itemId))}>
                    Start over
                  </Button>
                )
              }
            >
              <StepsChecklist steps={item.steps} checked={item.steps_checked} busy={busy} onToggle={toggleStep} />
            </Section>
          )}
          {item.facts.length > 0 && (
            <Section title="Key details">
              <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed">
                {item.facts.map((fact, index) => (
                  <li key={index}>{fact}</li>
                ))}
              </ul>
            </Section>
          )}
          {details?.transcript && (
            <Section
              title="Transcript"
              aside={
                <Button variant="ghost" size="sm" aria-expanded={showTranscript} onClick={() => setShowTranscript(!showTranscript)}>
                  {showTranscript ? "Hide" : "Show"}
                </Button>
              }
            >
              <p
                className={`whitespace-pre-line text-sm leading-relaxed text-zinc-700 dark:text-zinc-300 ${
                  showTranscript ? "" : "line-clamp-3"
                }`}
              >
                {details.transcript}
              </p>
            </Section>
          )}
        </div>

        <aside className="space-y-6">
          <Section title="Collections">
            {item.collections.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {item.collections.map((link) => (
                  <span
                    key={link.id}
                    className="inline-flex items-center gap-1 rounded-full bg-zinc-100 py-1 pl-2.5 pr-1 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                  >
                    <a href={`#/collections/${link.id}`} className="hover:text-indigo-700 dark:hover:text-indigo-300">
                      {collections.find((c) => c.id === link.id)?.path ?? link.name}
                    </a>
                    <span className="text-[10px] text-zinc-500 dark:text-zinc-400">
                      {{ user: "Added by you", ai: "Filed by AI", rule: "Matched a rule", platform: `From ${item.platform_name}` }[link.source]}
                    </span>
                    <button
                      type="button"
                      aria-label={`Take out of ${link.name}`}
                      onClick={() => void changeCollections(() => sortingApi.removeFrom(item.id, link.id))}
                      className="rounded-full px-1 text-zinc-400 hover:bg-zinc-200 hover:text-zinc-700 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-500 dark:text-zinc-400">Not in a collection yet.</p>
            )}
            {idea && (
              <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-zinc-50 px-2.5 py-2 text-xs dark:bg-zinc-800/60">
                <span className="text-zinc-500 dark:text-zinc-400">
                  AI suggests <b className="font-medium text-zinc-800 dark:text-zinc-100">{idea.collection.name}</b> ({idea.fit})
                </span>
                <Button size="sm" onClick={() => void changeCollections(() => sortingApi.accept(item.id, idea.collection.id))}>
                  Accept
                </Button>
              </div>
            )}
            {collections.length > 0 && (
              <div className="mt-3">
                <CollectionPicker
                  collections={collections}
                  spaces={spaces}
                  exclude={item.collections.map((link) => link.id)}
                  suggested={item.suggestions.map((pick) => pick.name)}
                  label="Add to a collection"
                  onPick={(collection) => void changeCollections(() => sortingApi.move(item.id, null, collection.id))}
                >
                  + Add to a collection
                </CollectionPicker>
              </div>
            )}
          </Section>
          <Section title="Tags">
            <TagEditor item={item} onChange={mergeCard} />
            <div className="mt-3">
              <TagIdeas
                item={item}
                onAnswer={(names, accept) => void changeCollections(() => sortingApi.answerTags(item.id, names, accept))}
              />
            </div>
          </Section>
          <Section title="Plans">
            {(item.plans ?? []).length > 0 && (
              <ul className="mb-2 space-y-1 text-sm">
                {(item.plans ?? []).map((plan) => (
                  <li key={plan.id}>
                    <a href={`#/plans/${plan.id}`} className="font-medium text-indigo-600 hover:underline dark:text-indigo-400">
                      {plan.name}
                    </a>
                    {plan.done && <span className="ml-2 text-xs text-emerald-600">ticked off</span>}
                  </li>
                ))}
              </ul>
            )}
            <PlanPanel item={item} onChange={mergeCard} />
          </Section>
          {item.caption && item.caption !== item.title && (
            <Section title="Caption">
              <p className="whitespace-pre-line text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{item.caption}</p>
            </Section>
          )}
          <p className="text-xs text-zinc-400 dark:text-zinc-500">
            Keys: <kbd>1</kbd>–<kbd>9</kbd> tick a step · <kbd>O</kbd> open video · <kbd>Esc</kbd> back
          </p>
        </aside>
      </div>
    </div>
  );
}

