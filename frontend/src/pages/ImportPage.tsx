// Import screen: drop an export zip or folder (or pick one), watch it
// import, and see what was found. Dropping anywhere on the page works.
import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";

import { icons } from "../components/icons";
import { Button, Card, Notice, inputClass } from "../components/ui";
import {
  filesFromDrop,
  filesFromInput,
  getSummary,
  importVideoLink,
  startImport,
  type DroppedFile,
  type LibrarySummary,
  type Upload,
} from "../features/import/importApi";
import { CopyingCard, JobCard, RecentImports } from "../features/import/ImportStatus";
import PlatformGuides from "../features/import/PlatformGuides";
import { announceChange } from "../features/organize/organizeApi";
import { errorText } from "../lib/api";
import { isActive, jobActions, useJobFinished, useJobs, type Job } from "../lib/jobs";

export default function ImportPage() {
  const jobs = useJobs();
  const [summary, setSummary] = useState<LibrarySummary | null>(null);
  const [copying, setCopying] = useState<{ sent: number; total: number } | null>(null);
  const [started, setStarted] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const upload = useRef<Upload | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => {
    getSummary().then(setSummary).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);
  useJobFinished(["import"], refresh);

  useEffect(() => {
    // "Choose folder" needs this attribute, which React doesn't know about.
    folderInput.current?.setAttribute("webkitdirectory", "");
  }, []);

  const importJobs = jobs.filter((job) => job.kind === "import");
  // An import still running when the page opened is followed to its end too.
  const [following, setFollowing] = useState<number | null>(null);
  const runningId = importJobs.find(isActive)?.id;
  useEffect(() => {
    if (runningId !== undefined) setFollowing(runningId);
  }, [runningId]);
  // The import to show: the one just started, else the one being followed.
  const currentId = started?.id ?? following ?? runningId;
  const current = importJobs.find((job) => job.id === currentId) ?? started ?? undefined;
  const earlier = importJobs.filter((job) => job.id !== current?.id).slice(0, 5);
  const busy = copying !== null || (current !== undefined && isActive(current));

  const begin = async (files: DroppedFile[]) => {
    if (busy || files.length === 0) return;
    setError(null);
    setStarted(null);
    setCopying({ sent: 0, total: 0 });
    const next = startImport(files, (sent, total) => setCopying({ sent, total }));
    upload.current = next;
    try {
      setStarted(await next.done);
    } catch (err) {
      if (errorText(err) !== "Cancelled") setError(errorText(err));
    } finally {
      upload.current = null;
      setCopying(null);
    }
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    // Must be read straight away: the browser empties the drop afterwards.
    filesFromDrop(event.dataTransfer).then(begin, (err) => setError(errorText(err)));
  };

  const onDragOver = (event: DragEvent) => {
    event.preventDefault();
    if (!busy) setDragging(true);
  };

  const onDragLeave = (event: DragEvent) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
  };

  return (
    <div
      className="mx-auto max-w-4xl space-y-8 px-8 py-10"
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      data-testid="import-page"
    >
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Import your saves</h1>
        <p className="mt-1 text-zinc-600 dark:text-zinc-400">
          Bring in what you've saved on TikTok, YouTube, Instagram and Facebook. Everything stays on this PC.
        </p>
      </header>

      <LibraryCounts summary={summary} />

      <PasteVideoLink onAdded={() => { refresh(); announceChange(); }} />

      <div
        className={`rounded-2xl border-2 border-dashed px-6 py-12 text-center transition ${
          dragging
            ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40"
            : "border-zinc-300 bg-white dark:border-zinc-700 dark:bg-zinc-900"
        }`}
      >
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 p-3 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
          {icons.import}
        </span>
        <p className="mt-4 text-lg font-medium">
          {dragging ? "Drop it to start the import" : "Drag your export zip or folder here"}
        </p>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          The zip you downloaded from TikTok, Google Takeout or Meta. Importing the same export again is safe: nothing
          is added twice.
        </p>
        <div className="mt-5 flex flex-wrap justify-center gap-2">
          <Button data-tour="import" onClick={() => fileInput.current?.click()} disabled={busy}>
            Choose zip file
          </Button>
          <Button variant="secondary" onClick={() => folderInput.current?.click()} disabled={busy}>
            Choose folder
          </Button>
        </div>
        <a href="#/collections/links" className="mt-3 inline-block text-sm underline">Choose where new saves go</a>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".zip,.json,.txt,.csv,.html"
          className="hidden"
          aria-label="Export file"
          onChange={(event) => {
            begin(filesFromInput(event.target.files));
            event.target.value = "";
          }}
        />
        <input
          ref={folderInput}
          type="file"
          className="hidden"
          aria-label="Export folder"
          onChange={(event) => {
            begin(filesFromInput(event.target.files));
            event.target.value = "";
          }}
        />
      </div>

      {error && <Notice tone="error">{error}</Notice>}
      {copying && <CopyingCard sent={copying.sent} total={copying.total} onCancel={() => upload.current?.cancel()} />}
      {!copying && current && (
        <JobCard job={current} onCancel={() => jobActions.cancel(current.id).catch(() => undefined)} />
      )}

      <RecentImports jobs={earlier} />

      <PlatformGuides />

      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Imports read your export files and video links. Your saves on the original platforms stay as they are.
      </p>
    </div>
  );
}

function PasteVideoLink({ onAdded }: { onAdded: () => void }) {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [forgotten, setForgotten] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ text: string; failed: boolean } | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await add(url.trim());
  }

  async function add(link: string, reimport = false) {
    if (busy || !link) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await importVideoLink(link, reimport);
      setForgotten(result.status === "deleted_before" ? result.url : null);
      if (result.status === "added") {
        setUrl("");
        onAdded();
      }
      const message = {
        added: `${result.platform_name} save added. You can get its transcript in Sort.`,
        already_had: "This save is already in Keptwise. Check Archive if it’s missing from the Library.",
        deleted_before: "You previously deleted this save permanently. Keptwise skipped it.",
      };
      setFeedback({ text: message[result.status], failed: false });
    } catch (error) {
      setFeedback({ text: errorText(error), failed: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h2 className="font-semibold">Add a video link</h2>
      <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">Paste a link from TikTok, YouTube, Instagram or Facebook.</p>
      <form onSubmit={submit} className="mt-3 flex flex-wrap gap-2">
        <input className={`${inputClass} min-w-48 flex-1`} type="text" inputMode="url" aria-label="Video link"
          placeholder="https://…" value={url} maxLength={4096} autoComplete="off" disabled={busy}
          onChange={(event) => { setUrl(event.target.value); setFeedback(null); setForgotten(null); }} />
        <Button type="submit" disabled={busy || !url.trim()}>{busy ? "Adding…" : "Add to Library"}</Button>
      </form>
      {feedback && <div className="mt-3"><Notice tone={feedback.failed ? "error" : "success"}>
        {feedback.text}{forgotten && <Button size="sm" className="ml-2" variant="secondary" disabled={busy}
          onClick={() => void add(forgotten, true)}>Import again as a new save</Button>}
      </Notice></div>}
    </Card>
  );
}

function LibraryCounts({ summary }: { summary: LibrarySummary | null }) {
  if (!summary) return null;
  return (
    <Card className="p-4">
      <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">In your library</p>
      <dl className="mt-2 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {summary.platforms.map((platform) => (
          <div key={platform.platform} className="rounded-xl bg-zinc-50 px-3 py-2 dark:bg-zinc-800/60">
            <dt className="text-xs text-zinc-500 dark:text-zinc-400">{platform.name}</dt>
            <dd className="text-xl font-semibold tabular-nums" data-testid={`count-${platform.platform}`}>
              {platform.count.toLocaleString("en-GB")}
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
