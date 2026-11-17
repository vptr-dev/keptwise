// "Update now": one click downloads the newest version from GitHub, checks
// it, installs it over this copy (keeping every save and setting) and opens
// Keptwise again. Shown in the sidebar and in Settings -> About and updates
// when a newer version exists. Running from source, it links to GitHub.
import { useState } from "react";

import { Button } from "../../components/ui";
import { errorText } from "../../lib/api";
import { isActive, useJobs, type Job } from "../../lib/jobs";
import { updatesApi, type UpdateStatus } from "./updatesApi";

// Update jobs started from this window. A finished or failed update job from
// an earlier run is history (the app was replaced since), so it isn't shown.
const startedHere = new Set<number>();

/** The update job to show: one that is running, or one started in this window. */
export function useUpdateJob(): Job | undefined {
  return useJobs().find((job) => job.kind === "update" && (isActive(job) || startedHere.has(job.id)));
}

export default function UpdateNow({ status, place }: { status: UpdateStatus; place: "sidebar" | "settings" }) {
  const job = useUpdateJob();
  const [problem, setProblem] = useState<string | null>(null);
  const [, setStarted] = useState(0);
  const running = job !== undefined && isActive(job);
  const finished = job?.status === "done" && (job.result as { updated?: boolean } | null)?.updated === true;
  const failed = job?.status === "failed";
  const error = problem ?? (failed ? job?.error : null);

  async function start() {
    setProblem(null);
    try {
      const started = await updatesApi.install();
      startedHere.add(started.id);
      setStarted(started.id);
    } catch (e) {
      setProblem(errorText(e));
    }
  }

  const sidebar = place === "sidebar";
  const box = `kw-glass rounded-xl border text-zinc-800 dark:text-zinc-100 ${
    sidebar ? "mx-3 mb-3 px-3 py-2.5 text-xs" : "px-4 py-3 text-sm"
  }`;
  const quiet = "text-zinc-500 dark:text-zinc-400";

  if (running || finished) {
    const share = job && job.total > 0 ? Math.min(100, Math.round((job.progress / job.total) * 100)) : null;
    const filling = share !== null && !finished;
    return (
      <div className={box} role="status">
        <p className="font-medium">{finished ? `Installing version ${status.latest}…` : job?.message ?? "Getting the update…"}</p>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-700">
          <div
            className={`h-full rounded-full bg-indigo-600 transition-[width] duration-300 dark:bg-indigo-400 ${filling ? "" : "w-full animate-pulse"}`}
            style={filling ? { width: `${share}%` } : undefined}
          />
        </div>
        <p className={`mt-1.5 ${quiet}`}>
          {finished ? "Keptwise will close and open again by itself." : "Your saves and settings stay as they are."}
        </p>
      </div>
    );
  }

  if (!status.update_available) return null;

  return (
    <div className={box}>
      <p className="flex items-center gap-2 font-medium">
        <span className="h-2 w-2 shrink-0 rounded-full bg-indigo-600 dark:bg-indigo-400" aria-hidden />
        Version {status.latest} is available
      </p>
      {!sidebar && !error && <p className={`mt-0.5 ${quiet}`}>Your saves and settings stay as they are.</p>}
      {error && <p className="mt-1 text-red-700 dark:text-red-300">{error}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        {status.can_install ? (
          <Button size="sm" onClick={() => void start()}>
            {error ? "Try again" : "Update now"}
          </Button>
        ) : (
          <a href={status.url} target="_blank" rel="noreferrer" className="font-medium underline underline-offset-2">
            Get it from GitHub
          </a>
        )}
        {status.can_install && (
          <a href={status.url} target="_blank" rel="noreferrer" className={`${quiet} hover:underline`}>
            What's new
          </a>
        )}
      </div>
    </div>
  );
}
