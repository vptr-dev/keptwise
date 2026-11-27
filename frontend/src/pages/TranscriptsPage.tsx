// Sort (#/sort): everything the AI does happens here, and nowhere else.
// 1. Get each video's details, picture and transcript. 2. The AI writes its
// notes and picks a collection and tags. 3. Approve its picks (Unsorted).
// Then: ask it again, or clear what it did. The other pages only show your
// saves and let you change them by hand. Each step runs in batches with
// live progress and Pause/Resume/Cancel.
import { onArchiveChange } from "../features/library/SaveControls";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { icons } from "../components/icons";
import { Button, Notice } from "../components/ui";
import EnrichJobCard from "../features/enrich/EnrichJobCard";
import { enrichApi, type EnrichOverview, type EnrichTarget, type RecentVideo } from "../features/enrich/enrichApi";
import RecentVideos from "../features/enrich/RecentVideos";
import TikTokAccess from "../features/enrich/TikTokAccess";
import { AiOptions, AskAgain, ClearAi } from "../features/sorting/AiTools";
import NotesStep from "../features/sorting/NotesStep";
import Unsorted from "../features/sorting/Unsorted";
import { errorText } from "../lib/api";
import { isActive, onJobUpdate, useJobs, type Job } from "../lib/jobs";
import { navigate, useRoute } from "../lib/router";

const BATCH_SIZES = [5, 50, 200];

export default function TranscriptsPage({ hideStats = false, onToggleStats }: {
  hideStats?: boolean; onToggleStats?: () => void;
}) {
  const { query } = useRoute();
  const jobs = useJobs();
  const [overview, setOverview] = useState<EnrichOverview | null>(null);
  const [recent, setRecent] = useState<RecentVideo[]>([]);
  const [started, setStarted] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(() => {
    enrichApi.overview().then(setOverview).catch((e) => setError(errorText(e)));
    enrichApi.recent().then(setRecent).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => onArchiveChange(refresh), [refresh]);

  // Each finished video moves the progress bar: show it in the list too.
  useEffect(() => {
    let last = -1;
    return onJobUpdate((job) => {
      if (job.kind !== "enrich") return;
      if (job.progress !== last || !isActive(job)) {
        last = job.progress;
        refresh();
      }
    });
  }, [refresh]);

  const enrichJobs = jobs.filter((job) => job.kind === "enrich");
  const running = enrichJobs.find(isActive);
  // The running job, otherwise the newest one (just started, or from before).
  const currentId = running?.id ?? Math.max(started?.id ?? 0, enrichJobs[0]?.id ?? 0);
  const current = enrichJobs.find((job) => job.id === currentId) ?? started ?? undefined;

  async function start(count: number | null, which: EnrichTarget = "waiting") {
    setBusy(true);
    setError(null);
    try {
      setStarted(await enrichApi.start(count, which));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const counts = overview?.counts;
  const speech = overview?.speech;
  const model = speech?.models.find((m) => m.id === speech.model);
  const nothingImported = counts !== undefined && counts.total === 0 && !counts.gone;

  return (
    <div className="mx-auto max-w-4xl space-y-4 px-4 py-8 lg:px-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Sort</h1>
        <p className="kw-tip mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Get transcripts, write notes, then approve where your saves go.
        </p>
      </header>

      {error && <Notice tone="error">{error}</Notice>}

      {nothingImported ? (
        <Notice>
          Nothing to do yet.{" "}
          <button type="button" className="font-medium underline" onClick={() => navigate("/import")}>
            Import your saves
          </button>{" "}
          first.
        </Notice>
      ) : (
        counts && (
          <SortSection step={1} title="Get transcripts" defaultOpen>
            {onToggleStats && <Button variant="ghost" size="sm" onClick={onToggleStats}>
              {hideStats ? "Show stats" : "Hide stats"}
            </Button>}
            {!hideStats && <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Count label="Waiting" value={counts.waiting} testId="count-waiting" />
            <Count label="Details ready" value={counts.done} testId="count-done" />
            <Count label="No speech detected" value={counts.no_speech} testId="count-no-speech" title="The speech model found no words. The clip may still have sound." />
            <Count label="Couldn't read" value={counts.failed} testId="count-failed" />
            <Count
              label="Unavailable"
              value={counts.gone ?? 0}
              testId="count-gone"
              href="#/archive/gone"
              title="Keptwise previously marked these videos as unavailable. You can check them again."
            />
          </dl>}
          {(counts.failed_reasons ?? []).length > 0 && (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-xs font-medium text-zinc-500 dark:text-zinc-400">Read errors</summary>
              <ul className="mt-2 space-y-1 text-xs text-zinc-600 dark:text-zinc-400">
                {(counts.failed_reasons ?? []).map((reason) => (
                  <li key={reason.text} className="flex gap-2">
                    <span className="w-10 shrink-0 text-right tabular-nums">{reason.count.toLocaleString("en-GB")}</span>
                    <span>{reason.text}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
            <p className="kw-tip mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              Start with a few saves. This runs on your PC.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              {BATCH_SIZES.filter((size) => size < counts.waiting).map((size) => (
                <Button
                  key={size}
                  variant={size === BATCH_SIZES[0] ? "primary" : "secondary"}
                  disabled={busy || running !== undefined}
                  onClick={() => start(size)}
                >
                  Next {size}
                </Button>
              ))}
              <Button
                variant={counts.waiting <= BATCH_SIZES[0] ? "primary" : "secondary"}
                disabled={busy || running !== undefined || counts.waiting === 0}
                onClick={() => start(null)}
              >
                All {counts.waiting.toLocaleString("en-GB")} waiting
              </Button>
            </div>
            {(counts.failed > 0 || counts.no_speech > 0 || !!counts.gone) && (
            <details className="rounded-xl border border-zinc-200 p-3 dark:border-zinc-800">
              <summary className="cursor-pointer text-sm font-medium">Retry and recheck</summary>
              <div className="mt-2 flex flex-wrap gap-2">
              {counts.failed > 0 && (
                <Button variant="ghost" disabled={busy || running !== undefined} onClick={() => start(null, "failed")}>
                  Try the {counts.failed.toLocaleString("en-GB")} failed again
                </Button>
              )}
              {counts.no_speech > 0 && (
                <Button variant="ghost" disabled={busy || running !== undefined} onClick={() => start(null, "no_speech")}>
                  Retry {counts.no_speech.toLocaleString("en-GB")} without speech
                </Button>
              )}
              {!!counts.gone && (
                <Button variant="ghost" disabled={busy || running !== undefined} onClick={() => start(null, "unavailable")}>
                  Recheck {counts.gone.toLocaleString("en-GB")} unavailable
                </Button>
              )}
              </div>
            </details>
            )}
            <TikTokAccess connected={overview?.tiktok_session ?? false} onChange={refresh} />
            {model && (
              <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
                Speech model: {model.label}
                {model.downloaded ? "" : " (downloads the first time, about " + Math.round(model.approx_bytes / 1e6) + " MB)"}.{" "}
                <button type="button" className="underline" onClick={() => navigate("/settings")}>
                  Change
                </button>
              </p>
            )}
          </SortSection>
        )
      )}

      {current && <EnrichJobCard job={current} />}

      {!nothingImported && (
        <>
          <SortSection step={2} title="Write notes" defaultOpen>
            <NotesStep transcribing={running !== undefined} />
          </SortSection>
          <SortSection step={3} title="Review suggestions">
            <Unsorted limit={5} />
          </SortSection>
        </>
      )}

      {(!nothingImported || query.has("options")) && (
        <SortSection key={query.has("options") ? "options-open" : "options"} title="Sorting options" defaultOpen={query.has("options")}>
          <AiOptions />
          <AskAgain />
          <ClearAi />
        </SortSection>
      )}
      {recent.length > 0 && <SortSection title="Recent transcripts"><RecentVideos videos={recent} embedded /></SortSection>}
    </div>
  );
}

function SortSection({
  title, step, defaultOpen = false, children,
}: { title: string; step?: number; defaultOpen?: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <details open={open} onToggle={(event) => {
      if (event.target === event.currentTarget) setOpen(event.currentTarget.open);
    }}
      className="group kw-glass rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <summary data-tour={step === 1 ? "sort" : step === 2 ? "notes" : step === 3 ? "review" : undefined}
        className="flex cursor-pointer list-none items-center gap-3 rounded-2xl px-4 py-3 font-medium focus-visible:outline-2 focus-visible:outline-indigo-500">
        {step !== undefined && <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-indigo-100 text-xs text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{step}</span>}
        <span className="flex-1">{title}</span>
        <span className="h-4 w-4 -rotate-90 text-zinc-500 transition-transform group-open:rotate-0" aria-hidden="true">{icons.down}</span>
      </summary>
      <div className="space-y-3 px-4 pb-4">{children}</div>
    </details>
  );
}

function Count({ label, value, testId, title, href }: { label: string; value: number; testId: string; title?: string; href?: string }) {
  const body = (
    <>
      <dt className="text-xs text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="text-xl font-semibold tabular-nums" data-testid={testId}>
        {value.toLocaleString("en-GB")}
      </dd>
    </>
  );
  const box = "block rounded-xl bg-zinc-50 px-3 py-2 dark:bg-zinc-800/60";
  return href && value > 0 ? (
    <a href={href} title={title} className={`${box} transition hover:bg-zinc-100 dark:hover:bg-zinc-800`}>
      {body}
    </a>
  ) : (
    <div title={title} className={box}>
      {body}
    </div>
  );
}
