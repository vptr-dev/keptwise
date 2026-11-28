// A background job: live progress with Pause, Resume and Cancel while it
// runs, and its summary (or what went wrong) when it ends.
import { useState, type ReactNode } from "react";

import { isActive, jobActions, type Job, type RemainingVideo } from "../lib/jobs";
import { errorText } from "../lib/api";
import ProgressBar from "./ProgressBar";
import { toast } from "./Toasts";
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
  const [hidden, setHidden] = useState<Job | null>(null);
  const dismiss = () => {
    setHidden(job);
    void jobActions.dismiss(job.id).catch(() => {
      setHidden((dismissed) => dismissed === job ? null : dismissed);
      toast("Couldn’t hide this notice. Try again.", { tone: "error" });
    });
  };
  if (isActive(job)) {
    const paused = job.status === "paused";
    return (
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate font-medium">{job.title}</h2>
            <p className="kw-tip text-sm text-zinc-500 dark:text-zinc-400" data-testid="job-message">
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
  if (hidden === job || job.notice_dismissed) return null;
  if (job.status === "failed" || job.status === "interrupted") {
    return (
      <Notice tone={job.status === "failed" ? "error" : "warning"} onClose={dismiss} closeLabel="Dismiss job notice">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">
              {job.status === "failed" ? `The ${name} stopped` : "The app was closed while this was running"}
            </p>
            <p className="mt-1">{job.error ?? "Finished videos are kept. Resume carries on with the rest."}</p>
          </div>
          <JobRetry job={job} />
        </div>
      </Notice>
    );
  }
  if (job.status === "cancelled") {
    return (
      <Notice onClose={dismiss} closeLabel="Dismiss job notice">
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
    <Notice tone={warn ? "warning" : "success"} onClose={dismiss} closeLabel="Dismiss job notice">
      <p className="font-medium">{job.message ?? "Done"}</p>
      {detail && <p className="mt-1 text-xs opacity-80">{detail}</p>}
    </Notice>
  );
}


function JobRetry({ job }: { job: Job }) {
  const [remaining, setRemaining] = useState<RemainingVideo[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const canPreview = ["enrich", "notes", "sort", "tags"].includes(job.kind);
  async function reviewOrResume() {
    setBusy(true);
    setError("");
    try {
      if (canPreview && remaining === null) setRemaining(await jobActions.remaining(job.id));
      else await jobActions.resume(job.id);
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  return <div className="space-y-2">
    {remaining && <div className="max-h-48 overflow-auto">
      <p className="font-medium">{remaining.length.toLocaleString()} videos left to review or retry</p>
      <ul className="space-y-1">
        {remaining.map(video => <li key={video.id}>
          <a className="underline" href={`#/item/${video.id}`}>{video.title}</a>
          <span className="block text-xs">{video.error ?? (video.unavailable ? "Unavailable on its platform" : "Waiting to be processed")}</span>
        </li>)}
      </ul>
    </div>}
    {error && <p role="alert">{error}</p>}
    <Button size="sm" disabled={busy || remaining?.length === 0} onClick={() => void reviewOrResume()}>
      {canPreview && remaining === null ? "Review remaining videos" : "Resume"}
    </Button>
  </div>;
}
