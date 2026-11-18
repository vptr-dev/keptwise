// Hidden developer page (Ctrl+Shift+D or #/dev): database numbers and a
// fake 10-second background job to watch live progress.
import { useCallback, useEffect, useState } from "react";

import ProgressBar from "../components/ProgressBar";
import { api, errorText } from "../lib/api";
import { isActive, jobActions, useJobs, type Job } from "../lib/jobs";

type Stats = {
  path: string;
  data_dir: string;
  size_bytes: number;
  schema_version: number;
  tables: Record<string, number>;
  items_by_status: Record<string, number>;
};

export default function DevPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const jobs = useJobs();

  const loadStats = useCallback(() => {
    api
      .get<Stats>("/api/dev/stats")
      .then(setStats)
      .catch((err) => setError(errorText(err)));
  }, []);

  useEffect(loadStats, [loadStats]);

  const startFakeJob = async () => {
    try {
      await api.post<Job>("/api/dev/fake-job");
      loadStats();
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold">Developer page</h1>
        <p className="kw-tip text-sm text-zinc-500">Database numbers and a test background job.</p>
      </header>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}</p>}

      <section className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-medium">Database</h2>
          <button type="button" onClick={loadStats} className="text-sm text-indigo-600 hover:underline">
            Refresh
          </button>
        </div>
        {stats ? (
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <dt className="text-zinc-500">Data folder</dt>
            <dd className="truncate font-mono" title={stats.data_dir}>{stats.data_dir}</dd>
            <dt className="text-zinc-500">Database size</dt>
            <dd>{(stats.size_bytes / 1024).toFixed(1)} KB</dd>
            <dt className="text-zinc-500">Schema version</dt>
            <dd>{stats.schema_version}</dd>
            {Object.entries(stats.tables).map(([table, count]) => (
              <Row key={table} label={`Rows in ${table}`} value={count} />
            ))}
          </dl>
        ) : (
          <p className="text-sm text-zinc-500">Loading…</p>
        )}
      </section>

      <section className="rounded-xl border border-zinc-200 p-5 dark:border-zinc-800">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-medium">Background jobs</h2>
          <button
            type="button"
            onClick={startFakeJob}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-500"
          >
            Start fake 10-second job
          </button>
        </div>
        <ul className="space-y-3">
          {jobs.slice(0, 8).map((job) => (
            <JobRow key={job.id} job={job} />
          ))}
          {jobs.length === 0 && <li className="text-sm text-zinc-500">No jobs yet.</li>}
        </ul>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: number }) {
  return (
    <>
      <dt className="text-zinc-500">{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

function JobRow({ job }: { job: Job }) {
  return (
    <li className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span>
          #{job.id} {job.title} · <span data-testid={`job-status-${job.id}`}>{job.status}</span>
        </span>
        {isActive(job) && (
          <span className="space-x-3">
            {job.status === "paused" ? (
              <button type="button" className="text-indigo-600" onClick={() => jobActions.resume(job.id)}>Resume</button>
            ) : (
              <button type="button" className="text-indigo-600" onClick={() => jobActions.pause(job.id)}>Pause</button>
            )}
            <button type="button" className="text-red-600" onClick={() => jobActions.cancel(job.id)}>Cancel</button>
          </span>
        )}
      </div>
      <ProgressBar done={job.progress} total={job.total} label={job.title} />
      <p className="text-xs text-zinc-500">{job.error ?? job.message ?? ""}</p>
    </li>
  );
}
