// Live job updates from the backend (Server-Sent Events on /api/events).
import { useEffect, useRef, useState } from "react";

import { api } from "./api";

export type JobStatus =
  | "queued"
  | "running"
  | "paused"
  | "done"
  | "failed"
  | "cancelled"
  | "interrupted";

export type Job = {
  id: number;
  kind: string;
  title: string;
  status: JobStatus;
  progress: number;
  total: number;
  message: string | null;
  error: string | null;
  params: Record<string, unknown>;
  result: Record<string, unknown> | null;
  created_at: string;
  finished_at: string | null;
  notice_dismissed?: boolean;
};

export const ACTIVE_STATUSES: JobStatus[] = ["queued", "running", "paused"];

export function isActive(job: Job): boolean {
  return ACTIVE_STATUSES.includes(job.status);
}

type Listener = (job: Job) => void;
const listeners = new Set<Listener>();
let source: EventSource | null = null;

// One shared connection for the whole window, opened on first use.
function connect(): void {
  if (source || typeof EventSource === "undefined") return;
  source = new EventSource("/api/events");
  source.addEventListener("job", (event) => {
    const job = JSON.parse((event as MessageEvent<string>).data) as Job;
    listeners.forEach((listener) => listener(job));
  });
}

export function onJobUpdate(listener: Listener): () => void {
  connect();
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** All recent jobs, kept up to date live. Newest first. */
export function useJobs(): Job[] {
  const [jobs, setJobs] = useState<Job[]>([]);
  useEffect(() => {
    let active = true;
    const stop = onJobUpdate((job) => setJobs((current) => mergeJobs([job], current)));
    api
      .get<Job[]>("/api/jobs")
      .then((list) => {
        if (active) setJobs((current) => mergeJobs(current, list));
      })
      .catch(() => undefined);
    return () => {
      active = false;
      stop();
    };
  }, []);
  return jobs;
}

function mergeJobs(incoming: Job[], current: Job[]): Job[] {
  const byId = new Map(current.map((job) => [job.id, job]));
  for (const job of incoming) byId.set(job.id, job);
  return [...byId.values()].sort((a, b) => b.id - a.id);
}

/** Calls `callback` once whenever a job of one of these kinds finishes. */
export function useJobFinished(kinds: string[], callback: (job: Job) => void): void {
  const saved = useRef(callback);
  saved.current = callback;
  const key = kinds.join(",");
  useEffect(() => {
    const wanted = key.split(",");
    return onJobUpdate((job) => {
      if (wanted.includes(job.kind) && !isActive(job)) saved.current(job);
    });
  }, [key]);
}

export const jobActions = {
  pause: (id: number) => api.post<Job>(`/api/jobs/${id}/pause`),
  resume: (id: number) => api.post<Job>(`/api/jobs/${id}/resume`),
  cancel: (id: number) => api.post<Job>(`/api/jobs/${id}/cancel`),
  dismiss: (id: number) => api.post<void>(`/api/jobs/${id}/dismiss-notice`),
};
