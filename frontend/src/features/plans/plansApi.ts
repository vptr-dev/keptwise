// Talking to the backend about Plans: saves and to-dos to work through,
// optionally for a day and split into sections, ticked off one by one.
import { api } from "../../lib/api";
import type { LibraryItem } from "../library/libraryApi";

export type PlanSummary = {
  id: number;
  name: string;
  note: string | null;
  color: string | null;
  done: boolean;
  done_at: string | null;
  created_at: string;
  updated_at: string;
  due_on: string | null;
  pinned: boolean;
  item_count: number;
  items_done: number;
  tasks_total: number;
  tasks_done: number;
  steps_done: number;
  steps_total: number;
  preview: { id: number; has_thumbnail: boolean }[];
  platforms: string[];
};

export type PlanEntry = { item: LibraryItem; done: boolean; done_at: string | null; section?: string | null; note?: string | null };
export type PlanTask = { id: number; text: string; section: string | null; done: boolean; done_at: string | null };
export type PlanDetails = PlanSummary & { items: PlanEntry[]; tasks?: PlanTask[]; sections?: string[]; added?: number };
export type PlansList = { plans: PlanSummary[]; open: number; finished: number };

export type PlanChange = {
  name?: string;
  note?: string | null;
  color?: string | null;
  done?: boolean;
  due_on?: string | null;
  pinned?: boolean;
};

export const plansApi = {
  list: () => api.get<PlansList>("/api/plans"),
  get: (id: number) => api.get<PlanDetails>(`/api/plans/${id}`),
  create: (name: string, itemIds: number[] = [], note?: string, extra: { collection_id?: number; due_on?: string } = {}) =>
    api.post<PlanDetails>("/api/plans", { name, item_ids: itemIds, note, ...extra }),
  change: (id: number, change: PlanChange) => api.patch<PlanDetails>(`/api/plans/${id}`, change),
  remove: (id: number) => api.del<PlansList>(`/api/plans/${id}`),
  copy: (id: number) => api.post<PlanDetails>(`/api/plans/${id}/copy`, {}),
  add: (id: number, itemIds: number[]) => api.post<PlanDetails>(`/api/plans/${id}/items`, { item_ids: itemIds }),
  removeItem: (id: number, itemId: number) => api.del<PlanDetails>(`/api/plans/${id}/items/${itemId}`),
  tick: (id: number, itemId: number, done: boolean) => api.put<PlanDetails>(`/api/plans/${id}/items/${itemId}`, { done }),
  changeItem: (id: number, itemId: number, change: { section?: string | null; note?: string | null }) =>
    api.patch<PlanDetails>(`/api/plans/${id}/items/${itemId}`, change),
  reorder: (id: number, itemIds: number[]) => api.post<PlanDetails>(`/api/plans/${id}/order`, { item_ids: itemIds }),
  addTask: (id: number, text: string, section: string | null = null) =>
    api.post<PlanDetails>(`/api/plans/${id}/tasks`, { text, section }),
  changeTask: (id: number, taskId: number, change: { text?: string; section?: string | null; done?: boolean }) =>
    api.patch<PlanDetails>(`/api/plans/${id}/tasks/${taskId}`, change),
  removeTask: (id: number, taskId: number) => api.del<PlanDetails>(`/api/plans/${id}/tasks/${taskId}`),
  /** Rename a section, or pass null to dissolve it (what's in it stays). */
  renameSection: (id: number, old: string, next: string | null) =>
    api.post<PlanDetails>(`/api/plans/${id}/sections`, { old, new: next }),
};

/** 0..1 over saves and to-dos together. */
export function planProgress(plan: Pick<PlanSummary, "item_count" | "items_done"> & Partial<Pick<PlanSummary, "tasks_total" | "tasks_done">>): number {
  const total = plan.item_count + (plan.tasks_total ?? 0);
  return total ? (plan.items_done + (plan.tasks_done ?? 0)) / total : 0;
}

function localDay(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Days from today to a "2026-12-24" day: 0 today, 1 tomorrow, -1 yesterday. */
export function daysUntil(day: string, today: Date = new Date()): number {
  const [y, m, d] = day.split("-").map(Number);
  const then = Date.UTC(y, m - 1, d);
  const [ty, tm, td] = localDay(today).split("-").map(Number);
  return Math.round((then - Date.UTC(ty, tm - 1, td)) / 86_400_000);
}

/** A short label and colour for when a plan is for, or null without a day. */
export function dueText(day: string | null, done = false, today: Date = new Date()): { text: string; tone: string; late: boolean } | null {
  if (!day) return null;
  const n = daysUntil(day, today);
  const calm = "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300";
  const soon = "bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200";
  const late = "bg-red-100 text-red-800 dark:bg-red-900/60 dark:text-red-200";
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const named = date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", ...(y !== today.getFullYear() ? { year: "numeric" } : {}) });
  if (done) return { text: named, tone: calm, late: false };
  if (n === 0) return { text: "Today", tone: soon, late: false };
  if (n === 1) return { text: "Tomorrow", tone: soon, late: false };
  if (n < 0) return { text: n === -1 ? "Yesterday" : `${-n} days late`, tone: late, late: true };
  if (n < 7) return { text: `In ${n} days · ${named}`, tone: calm, late: false };
  return { text: named, tone: calm, late: false };
}
