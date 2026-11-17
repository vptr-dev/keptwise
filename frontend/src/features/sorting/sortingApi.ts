// Talking to the backend about AI notes, collections and sorting.
import { api } from "../../lib/api";
import type { Job } from "../../lib/jobs";

export type Collection = {
  id: number;
  name: string;
  origin: "mine" | "ai" | "platform";
  description: string | null;
  position: number;
  count: number;
  parent_id: number | null; // the collection it's inside (null = at the top of its space)
  space_id?: number; // the space it's in
  total?: number; // its saves plus those of everything inside it
  ai_allowed: boolean; // the AI may file videos here
  color: string | null;
  icon?: string | null; // a small picture on its folder (see collectionIcons)
  collapsed: boolean; // its sub-collections are folded away in the sidebar
  path: string; // "Outer / Inner / Name"
  depth: number; // 0 at the top of a space
  has_children: boolean;
  done_count?: number;
  ai_count?: number; // how many of its saves the AI put there
};

export type LibraryCounts = { waiting: number; processed: number; review: number; unsorted: number; untagged?: number };

export type Space = { id: number; name: string; color: string | null; position: number; collections: number };

export type CollectionsOverview = {
  collections: Collection[];
  spaces?: Space[];
  counts: LibraryCounts;
  limit?: number; // the most collections one space holds (50)
  space_limit?: number; // the most spaces (8)
  depth_limit?: number; // how deep collections can sit inside each other (5)
  created_space?: number;
  moved_to?: number;
  per_save?: number; // the most one save can be in (10)
  created_id?: number;
};
export const COLLECTION_LIMIT = 50;
export const COLLECTIONS_PER_SAVE = 10;

export type ItemLink = {
  id: number;
  name: string;
  origin: string;
  source: "user" | "rule" | "ai" | "platform";
  confidence: number | null;
};

export type ItemCard = {
  id: number;
  platform: string;
  platform_name: string;
  url: string;
  author: string | null;
  duration_s: number | null;
  status: string;
  has_thumbnail: boolean;
  title: string | null;
  caption: string | null;
  summary: string | null;
  kind: string | null;
  kind_label: string | null;
  facts: string[];
  steps: string[];
  tags: string[];
  tag_list?: { id: number; name: string; color: string | null; source: "user" | "ai" | "rule" | "auto" }[];
  needs_review: boolean;
  review_reason: string | null;
  suggestions: { name: string; confidence: number }[];
  new_collection: string | null;
  error: string | null;
  collections: ItemLink[];
  plans?: { id: number; name: string; done: boolean }[];
};

export type View =
  | { type: "review" }
  | { type: "unsorted" }
  | { type: "all" }
  | { type: "collection"; id: number };

export type Rule = { field: "author" | "text"; value: string; collection: string; tag?: string };

export type SortingSettings = {
  auto_sort?: boolean; // the AI files a save when it writes its notes
  auto_tag?: boolean; // ...and tags it
  auto_notes?: boolean; // notes start by themselves when a transcripts job ends (local AI only)
  look_at_pictures?: boolean; // the AI also looks at pictures from the video
  mode: "my_list" | "my_list_plus_ideas";
  platform_collections: "hint" | "ignore";
  max_collections: number;
  rules: Rule[];
  review_below: number;
  kind_steps: Record<string, string>;
  safe_to_unsave: "processed" | "done" | "manual";
  ai_folder: string;
  tags_per_video: number;
  tag_mode: "free" | "prefer_mine" | "only_mine";
  my_tags: string[];
  no_collection_tag: string;
};

export type SortingSettingsResponse = {
  settings: SortingSettings;
  kinds: { id: string; label: string; default: string }[];
};

export type NotesOverview = {
  counts: LibraryCounts;
  ai_label: string;
  is_cloud: boolean;
  cloud_batch_limit: number;
};

function viewQuery(view: View, includeSub: boolean): string {
  return view.type === "collection"
    ? `view=collection&collection_id=${view.id}${includeSub ? "&include_sub=true" : ""}`
    : `view=${view.type}`;
}

export const sortingApi = {
  collections: () => api.get<CollectionsOverview>("/api/collections"),
  createCollection: (name: string) => api.post<CollectionsOverview>("/api/collections", { name }),
  renameCollection: (id: number, name: string) => api.patch<CollectionsOverview>(`/api/collections/${id}`, { name }),
  deleteCollection: (id: number) => api.del<CollectionsOverview>(`/api/collections/${id}`),
  library: (view: View, includeSub = false) => api.get<ItemCard[]>(`/api/library?${viewQuery(view, includeSub)}`),
  move: (itemId: number, fromId: number | null, toId: number) =>
    api.post<ItemCard>(`/api/items/${itemId}/move`, { from_id: fromId, to_id: toId }),
  removeFrom: (itemId: number, collectionId: number) =>
    api.del<ItemCard>(`/api/items/${itemId}/collections/${collectionId}`),
  accept: (itemId: number, choice: { collection_id?: number; new_name?: string }) =>
    api.post<ItemCard>(`/api/review/${itemId}/accept`, choice),
  overview: () => api.get<NotesOverview>("/api/notes/overview"),
  startNotes: (count: number | null, confirmCost = false) =>
    api.post<Job>("/api/notes/start", { count, confirm_cost: confirmCost }),
  resort: (which: "all" | "review" | "unsorted", keepManual: boolean, confirmCost = false, itemIds?: number[]) =>
    api.post<Job>("/api/sorting/resort", { which, keep_manual: keepManual, confirm_cost: confirmCost, item_ids: itemIds }),
  aiTags: (which: "untagged" | "with_notes", confirmCost = false, itemIds?: number[]) =>
    api.post<Job>("/api/tags/ai", { which, confirm_cost: confirmCost, item_ids: itemIds }),
  getSettings: () => api.get<SortingSettingsResponse>("/api/sorting/settings"),
  saveSettings: (settings: SortingSettings) => api.put<SortingSettingsResponse>("/api/sorting/settings", settings),
};

/** "Drag" data: which item, and which collection it was dragged out of. */
export const DRAG_TYPE = "application/x-saves-item";
export type DragData = { itemId: number; fromId: number | null };
