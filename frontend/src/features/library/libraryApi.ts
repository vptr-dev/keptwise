// Talking to the backend about the Library grid, an item's checklist,
// the Unsave list and the sidebar counts.
import { api } from "../../lib/api";
import type { ItemCard } from "../sorting/sortingApi";

/** An item card with the user's own progress on it. */
export type LibraryItem = ItemCard & {
  steps_checked: boolean[];
  saved_at: string | null;
  platform_collection: string | null;
  done: boolean;
  started_at: string | null;
  safe_to_unsave: boolean;
  unsaved: boolean;
  unsaved_at?: string | null;
  deleted?: boolean; // in the Archive (deleted by the user)
  deleted_at?: string | null;
  plans?: { id: number; name: string; done: boolean }[]; // the plans it's in
};

export type StatusFilter = "all" | "processed" | "waiting" | "failed";
export type ProgressFilter = "any" | "not_started" | "started" | "done";
export type SortOrder =
  | "newest"
  | "oldest"
  | "title"
  | "title_desc"
  | "posted_newest"
  | "posted_oldest"
  | "creator"
  | "longest"
  | "shortest"
  | "recently_sorted"
  | "most_steps";

export const SORT_LABELS: Record<SortOrder, string> = {
  newest: "Newest saved",
  oldest: "Oldest saved",
  title: "Title A–Z",
  title_desc: "Title Z–A",
  posted_newest: "Newest posted",
  posted_oldest: "Oldest posted",
  creator: "Creator A–Z",
  longest: "Longest first",
  shortest: "Shortest first",
  recently_sorted: "Recently sorted",
  most_steps: "Most steps",
};
const SORTS = Object.keys(SORT_LABELS) as SortOrder[];

export type LibraryQuery = {
  status: StatusFilter;
  progress: ProgressFilter;
  platform: string;
  kind: string;
  collection_id: string; // a collection's id, "none" = in no collection, "" = any
  tag: string;
  tags: string; // several tags, comma separated: saves with all of them
  creator: string;
  q: string; // words anywhere: title, caption, transcript, notes, tags
  sort: SortOrder;
};

export const DEFAULT_QUERY: LibraryQuery = {
  status: "all",
  progress: "any",
  platform: "",
  kind: "",
  collection_id: "",
  tag: "",
  tags: "",
  creator: "",
  q: "",
  sort: "newest",
};

export type FilterChoice = { id: string | number; label: string; count: number; depth?: number };
export type LibraryFilters = {
  platforms: FilterChoice[];
  kinds: FilterChoice[];
  collections: FilterChoice[];
  tags: FilterChoice[];
  creators: FilterChoice[];
  no_collection: number;
};
export type LibraryPage = { total: number; offset: number; items: LibraryItem[] };

export type OverviewCounts = {
  total: number;
  processed: number;
  waiting: number;
  ready_for_notes: number;
  failed: number;
  review: number;
  in_progress: number;
  done: number;
  to_unsave: number;
  unsaved: number;
  open_plans: number;
};
export type Overview = { counts: OverviewCounts; recent: LibraryItem[] };

/** Parts of the Archive: none = the Library itself. */
export type ArchivePart = "none" | "deleted" | "unsaved" | "gone";
export type UnsaveList = { items: LibraryItem[]; left: number };
export type ItemPage = { item: LibraryItem; transcript: string | null };

export const PAGE_SIZE = 60;

/** Only the filters that differ from the defaults, for the address bar. */
export function queryToParams(query: LibraryQuery): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query) as [keyof LibraryQuery, string][]) {
    if (value && value !== DEFAULT_QUERY[key]) params.set(key, value);
  }
  return params;
}

export function paramsToQuery(params: URLSearchParams): LibraryQuery {
  const read = <T extends string>(key: keyof LibraryQuery, allowed?: readonly T[]): T => {
    const value = params.get(key) ?? "";
    if (allowed && !allowed.includes(value as T)) return DEFAULT_QUERY[key] as T;
    return value as T;
  };
  return {
    status: read("status", ["all", "processed", "waiting", "failed"] as const),
    progress: read("progress", ["any", "not_started", "started", "done"] as const),
    platform: read("platform"),
    kind: read("kind"),
    collection_id: read("collection_id"),
    tag: read("tag"),
    tags: read("tags"),
    creator: read("creator"),
    q: read("q"),
    sort: read("sort", SORTS),
  };
}

/** The address parameters for the backend (collection "none" means "in no collection"). */
function backendParams(query: LibraryQuery): URLSearchParams {
  const params = queryToParams(query);
  if (query.collection_id === "none") {
    params.delete("collection_id");
    params.set("in_collection", "none");
  }
  return params;
}

export const libraryApi = {
  /** includeSub false: a collection's own saves, not those of the collections inside it. */
  /** archive: "deleted" lists the saves you deleted, "unsaved" the ones you've unsaved on the platform,
   * "gone" the ones taken down on the platform. */
  items: (query: LibraryQuery, offset = 0, includeSub = true, archive: ArchivePart = "none") => {
    const params = backendParams(query);
    if (!includeSub) params.set("include_sub", "false");
    if (archive !== "none") params.set("archive", archive);
    params.set("offset", String(offset));
    params.set("limit", String(PAGE_SIZE));
    return api.get<LibraryPage>(`/api/library/items?${params}`);
  },
  filters: () => api.get<LibraryFilters>("/api/library/filters"),
  overview: () => api.get<Overview>("/api/overview"),
  item: (id: number) => api.get<ItemPage>(`/api/items/${id}`),
  tick: (id: number, index: number, done: boolean) => api.put<LibraryItem>(`/api/items/${id}/steps/${index}`, { done }),
  patch: (id: number, change: Partial<Pick<LibraryItem, "done" | "safe_to_unsave" | "unsaved" | "deleted">> & { unavailable?: boolean }) =>
    api.patch<LibraryItem>(`/api/items/${id}`, change),
  /** Delete a save for good (only from the Archive). */
  purge: (id: number) => api.del<{ purged: number }>(`/api/items/${id}`),
  archiveCounts: () => api.get<{ deleted: number; unsaved: number; gone: number }>("/api/archive"),
  restart: (id: number) => api.post<LibraryItem>(`/api/items/${id}/restart`),
  unsave: () => api.get<UnsaveList>("/api/unsave"),
  clearUnsave: () => api.post<{ cleared: number }>("/api/unsave/clear"),
  exportCsv: () => api.post<{ path: string; count: number }>("/api/unsave/export"),
  openDownloads: () => api.post<{ opened: boolean }>("/api/unsave/open-folder"),
  /** Open the save on its platform in the normal web browser. */
  openInBrowser: (id: number) => api.post<{ opened: boolean }>(`/api/items/${id}/open`),
};

/** A title for every item, even ones the AI hasn't seen yet. */
export function displayTitle(item: Pick<ItemCard, "title" | "platform_name">): string {
  return item.title?.trim() || `${item.platform_name} video`;
}

/** "12 Mar 2026" */
export function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function stepProgress(item: Pick<LibraryItem, "steps" | "steps_checked">): { done: number; total: number } {
  return { done: item.steps_checked.filter(Boolean).length, total: item.steps.length };
}

