// Sort (#/sort): everything the AI does happens here, and nowhere else.
// 1. Get each video's details, picture and transcript. 2. The AI writes its
// notes and picks a collection and tags. 3. Approve its picks (Unsorted).
// Then: ask it again, or clear what it did. The other pages only show your
// saves and let you change them by hand. Each step runs in batches with
// live progress and Pause/Resume/Cancel.
import { useCallback, useEffect, useState } from "react";

import { Button, Card, Notice } from "../components/ui";
import EnrichJobCard from "../features/enrich/EnrichJobCard";
import { enrichApi, type EnrichOverview, type RecentVideo } from "../features/enrich/enrichApi";
import RecentVideos from "../features/enrich/RecentVideos";
import { AiOptions, AskAgain, ClearAi } from "../features/sorting/AiTools";
import NotesStep from "../features/sorting/NotesStep";
import Unsorted from "../features/sorting/Unsorted";
import { errorText } from "../lib/api";
import { isActive, onJobUpdate, useJobs, type Job } from "../lib/jobs";
import { navigate, useRoute } from "../lib/router";

const BATCH_SIZES = [5, 50, 200];

export default function TranscriptsPage() {
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

  async function start(count: number | null, which: "waiting" | "failed" = "waiting") {
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
  const nothingImported = counts !== undefined && counts.total === 0;

  return (
    <div className="mx-auto max-w-4xl space-y-8 px-8 py-10">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Sort</h1>
        <p className="kw-tip mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Everything the AI does happens here. The app reads each saved video's public page and writes down what's said
          (on this PC, for free); the AI writes notes and suggests where each save goes and how to tag it; you approve.
          The other pages are yours to look through and change by hand.
        </p>
      </header>

      {counts && (
        <Card className="p-4">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            <Count label="Waiting" value={counts.waiting} testId="count-waiting" />
            <Count label="Done" value={counts.done} testId="count-done" />
            <Count label="No sound" value={counts.no_speech} testId="count-no-speech" title="Read fine, but the video has no sound or speech: the notes use the caption and pictures." />
            <Count label="Couldn't read" value={counts.failed} testId="count-failed" />
            <Count
              label="Taken down"
              value={counts.gone ?? 0}
              testId="count-gone"
              href="#/archive/gone"
              title="Deleted on the platform. They're in Archive → Deleted TikToks."
            />
          </dl>
          {(counts.failed_reasons ?? []).length > 0 && (
            <details className="mt-3 text-sm">
              <summary className="cursor-pointer text-xs font-medium text-zinc-500 dark:text-zinc-400">Why some couldn't be read</summary>
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
        </Card>
      )}

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
          <Card>
            <h2 className="flex items-center gap-2 font-medium">
              <Step n={1} />
              Get transcripts
            </h2>
            <p className="kw-tip mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Newest saves first. You can pause, cancel or close the app at any time; finished videos are kept.
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
              {counts.failed > 0 && (
                <Button variant="ghost" disabled={busy || running !== undefined} onClick={() => start(null, "failed")}>
                  Try the {counts.failed.toLocaleString("en-GB")} failed again
                </Button>
              )}
            </div>
            {model && (
              <p className="mt-4 text-xs text-zinc-500 dark:text-zinc-400">
                Speech model: {model.label}
                {model.downloaded ? "" : " (downloads the first time, about " + Math.round(model.approx_bytes / 1e6) + " MB)"}.{" "}
                <button type="button" className="underline" onClick={() => navigate("/settings")}>
                  Change
                </button>
              </p>
            )}
          </Card>
        )
      )}

      {current && <EnrichJobCard job={current} />}

      {!nothingImported && (
        <>
          <StepTitle n={2} />
          <NotesStep transcribing={running !== undefined} />
          <StepTitle n={3} />
          <Unsorted limit={5} />
          <AskAgain />
          <ClearAi />
        </>
      )}

      {(!nothingImported || query.has("options")) && <AiOptions />}
      <RecentVideos videos={recent} />
    </div>
  );
}

function Step({ n }: { n: number }) {
  return (
    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-semibold text-white" aria-hidden="true">
      {n}
    </span>
  );
}

/** A thin line with the step's number, between the steps. */
function StepTitle({ n }: { n: number }) {
  return (
    <div className="flex items-center gap-3" aria-hidden="true">
      <Step n={n} />
      <span className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{n === 2 ? "Then the notes" : "Then approve where they go"}</span>
      <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
    </div>
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
