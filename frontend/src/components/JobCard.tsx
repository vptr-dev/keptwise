// A background job: live progress with Pause, Resume and Cancel while it
// runs, and its summary (or what went wrong) when it ends.
import type { ReactNode } from "react";

import { isActive, jobActions, type Job } from "../lib/jobs";
import ProgressBar from "./ProgressBar";
import { Button, Card, Notice } from "./ui";

export default function JobCard({
  job,
  name,
  detail,
  warn = false,
}: {
  job: Job;
  name: string; // "transcripts job", "AI notes job"
  detail?: ReactNode; // extra line under a finished job's summary
  warn?: boolean; // finished, but nothing worked: show it in amber
}) {
  if (isActive(job)) {
    const paused = job.status === "paused";
    return (
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate font-medium">{job.title}</h2>
            <p className="text-sm text-zinc-500 dark:text-zinc-400" data-testid="job-message">
              {paused ? "Paused. Press Resume to carry on." : job.message ?? "Waiting to start…"}
            </p>
          </div>
          <div className="flex gap-2">
            {paused ? (
              <Button size="sm" onClick={() => jobActions.resume(job.id)}>
                Resume
              </Button>
            ) : (
              <Button variant="secondary" size="sm" onClick={() => jobActions.pause(job.id)}>
                Pause
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={() => jobActions.cancel(job.id)}>
              Cancel
            </Button>
          </div>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <ProgressBar done={job.progress} total={job.total} label={job.title} />
          {job.total > 0 && (
            <span className="shrink-0 text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
              {job.progress.toLocaleString("en-GB")} / {job.total.toLocaleString("en-GB")}
            </span>
          )}
        </div>
      </Card>
    );
  }
  if (job.status === "failed" || job.status === "interrupted") {
    return (
      <Notice tone={job.status === "failed" ? "error" : "warning"}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">
              {job.status === "failed" ? `The ${name} stopped` : "The app was closed while this was running"}
            </p>
            <p className="mt-1">{job.error ?? "Finished videos are kept. Resume carries on with the rest."}</p>
          </div>
          <Button size="sm" onClick={() => jobActions.resume(job.id)}>
            Resume
          </Button>
        </div>
      </Notice>
    );
  }
  if (job.status === "cancelled") {
    return (
      <Notice>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>Cancelled. The videos that were finished are kept.</span>
          <Button variant="secondary" size="sm" onClick={() => jobActions.resume(job.id)}>
            Resume
          </Button>
        </div>
      </Notice>
    );
  }
  return (
    <Notice tone={warn ? "warning" : "success"}>
      <p className="font-medium">{job.message ?? "Done"}</p>
      {detail && <p className="mt-1 text-xs opacity-80">{detail}</p>}
    </Notice>
  );
}
