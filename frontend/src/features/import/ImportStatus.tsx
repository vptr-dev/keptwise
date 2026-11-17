// The card that shows the import in progress, and what it found afterwards.
import ProgressBar from "../../components/ProgressBar";
import { Badge, Button, Card, Notice, formatBytes } from "../../components/ui";
import { isActive, type Job } from "../../lib/jobs";
import type { ImportResult } from "./importApi";

export function CopyingCard({ sent, total, onCancel }: { sent: number; total: number; onCancel: () => void }) {
  return (
    <Card>
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <h2 className="font-medium">Copying your export into the app…</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            {total > 0 ? `${formatBytes(sent)} of ${formatBytes(total)}` : "Getting started"}
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      <div className="mt-4">
        <ProgressBar done={sent} total={total} label="Copying files" />
      </div>
    </Card>
  );
}

export function JobCard({ job, onCancel }: { job: Job; onCancel: () => void }) {
  if (isActive(job)) {
    return (
      <Card>
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <h2 className="truncate font-medium">{job.title}</h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">{job.message ?? "Waiting to start…"}</p>
          </div>
          <Button variant="secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
        </div>
        <div className="mt-4">
          <ProgressBar done={job.progress} total={job.total} label={job.title} />
        </div>
      </Card>
    );
  }
  if (job.status === "failed") {
    return (
      <Notice tone="error">
        <p className="font-medium">The import didn't work</p>
        <p className="mt-1">{job.error}</p>
      </Notice>
    );
  }
  if (job.status !== "done") {
    return <Notice tone="info">{job.message ?? "The import stopped."}</Notice>;
  }
  return <ResultCard result={job.result as ImportResult | null} message={job.message} />;
}

function ResultCard({ result, message }: { result: ImportResult | null; message: string | null }) {
  return (
    <Card>
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="h-4 w-4" aria-hidden="true">
            <path d="M5 12l5 5L20 7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-medium">Import finished</h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">{message}</p>
        </div>
      </div>
      {result && result.platforms.length > 0 && (
        <ul className="mt-4 divide-y divide-zinc-200 dark:divide-zinc-800">
          {result.platforms.map((platform) => (
            <li key={platform.platform} className="py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{platform.name}</span>
                <Badge tone="green">{platform.new.toLocaleString("en-GB")} new</Badge>
                {platform.already_had > 0 && <Badge>{platform.already_had.toLocaleString("en-GB")} already here</Badge>}
              </div>
              {platform.collections.length > 0 && (
                <p className="mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">
                  Collections: {platform.collections.join(", ")}
                </p>
              )}
              {platform.notes.map((note) => (
                <p key={note} className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  {note}
                </p>
              ))}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function RecentImports({ jobs }: { jobs: Job[] }) {
  if (jobs.length === 0) return null;
  return (
    <section>
      <h2 className="mb-2 text-sm font-medium text-zinc-500 dark:text-zinc-400">Earlier imports</h2>
      <ul className="divide-y divide-zinc-200 rounded-2xl border border-zinc-200 bg-white text-sm dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
        {jobs.map((job) => (
          <li key={job.id} className="flex items-center gap-3 px-4 py-2.5">
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{job.title}</span>
              <span className="block truncate text-zinc-500 dark:text-zinc-400">
                {job.status === "failed" ? job.error : job.message}
              </span>
            </span>
            <StatusBadge job={job} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function StatusBadge({ job }: { job: Job }) {
  if (job.status === "done") return <Badge tone="green">Done</Badge>;
  if (job.status === "failed") return <Badge tone="red">Failed</Badge>;
  if (isActive(job)) return <Badge tone="indigo">Running</Badge>;
  return <Badge tone="amber">Stopped</Badge>;
}
