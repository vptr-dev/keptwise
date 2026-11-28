// Talking to the backend about folders, tags and doing things to many saves
// at once. Also the "something changed" signal the sidebar listens to.
import { api } from "../../lib/api";
import type { CollectionsOverview, ItemCard } from "../sorting/sortingApi";

export type Tag = {
  id: number;
  name: string;
  color: string | null;
  count: number;
  by_user?: number; // how many of those saves got it from the user, the AI, or the app's rules
  by_ai?: number;
  by_app?: number;
  created_at?: string;
};
export type TagsList = { tags: Tag[]; created_id?: number; per_save?: number; limit?: number; total?: number };
export const TAGS_PER_SAVE = 10;
export const TAG_LIMIT = 100; // different tags the app holds

export type BulkAction =
  | "add_to"
  | "move_to"
  | "remove_from"
  | "add_tag"
  | "remove_tag"
  | "done"
  | "not_done"
  | "add_to_plan"
  | "safe"
  | "not_safe"
  | "unsaved"
  | "still_saved"
  | "delete" // to the Archive
  | "restore"
  | "purge"; // for good (only saves already in the Archive)
export type BulkBody = {
  item_ids: number[];
  action: BulkAction;
  collection_id?: number;
  from_id?: number | null;
  tag?: string;
  plan_id?: number;
};

export type PlatformLink = {
  platform: string;
  platform_name: string;
  name: string; // the collection's name on the platform
  count: number; // saves the export says are in it
  membership_known: boolean; // false for TikTok: its export only lists the names
  collection_id: number | null; // the app collection it's linked to
  collection_name: string | null;
  mode: "auto" | "manual";
  filed: number; // of its saves, how many are in the linked collection
};
export type PlatformLinks = {
  links: PlatformLink[];
  import_destinations?: ImportDestination[];
  room_left: number;
  unconfirmed_memberships?: number;
  filed?: number;
  made?: number; // transfer: new collections made
  linked?: number; // transfer: platform collections linked
  no_room?: number; // transfer: left out because the space is full
};

export type ImportDestination = Pick<PlatformLink, "platform" | "platform_name" | "collection_id">;

export type CollectionChange = {
  name?: string;
  description?: string;
  ai_allowed?: boolean;
  color?: string;
  clear_color?: boolean;
  icon?: string | null;
  collapsed?: boolean;
};

export const COLORS = ["violet", "indigo", "blue", "teal", "emerald", "amber", "rose", "zinc"] as const;
// "accent" (or no colour): follows the accent colour.
export type ColorName = (typeof COLORS)[number];

// A dot of each colour (plain classes so Tailwind keeps them).
export const COLOR_DOTS: Record<string, string> = {
  accent: "bg-indigo-500",
  violet: "bg-[#8b5cf6]",
  indigo: "bg-[#6366f1]",
  blue: "bg-[#3b82f6]",
  teal: "bg-[#14b8a6]",
  emerald: "bg-[#10b981]",
  amber: "bg-[#f59e0b]",
  rose: "bg-[#f43f5e]",
  zinc: "bg-[#a1a1aa]",
};

export const organizeApi = {
  tags: () => api.get<TagsList>("/api/tags"),
  createTag: (name: string) => api.post<TagsList>("/api/tags", { name }),
  changeTag: (id: number, change: { name?: string; color?: string }) => api.patch<TagsList>(`/api/tags/${id}`, change),
  deleteTag: (id: number) => api.del<TagsList>(`/api/tags/${id}`),
  mergeTags: (ids: number[], into: string) => api.post<TagsList>("/api/tags/merge", { tag_ids: ids, into }),
  deleteTags: (ids: number[]) => api.post<TagsList>("/api/tags/delete", { tag_ids: ids }),
  tagItem: (itemId: number, name: string) => api.post<ItemCard>(`/api/items/${itemId}/tags`, { name }),
  untagItem: (itemId: number, tagId: number) => api.del<ItemCard>(`/api/items/${itemId}/tags/${tagId}`),
  bulk: (body: BulkBody) =>
    api.post<{ changed: number; skipped_full?: number; items: ItemCard[] }>("/api/items/bulk", body),
  mergeCollection: (id: number, intoId: number) =>
    api.post<CollectionsOverview>(`/api/collections/${id}/merge`, { into_id: intoId }),
  platformLinks: (spaceId?: number) => api.get<PlatformLinks>(`/api/platform-collections${spaceId ? `?space_id=${spaceId}` : ""}`),
  setImportDestination: (platform: string, collectionId: number | null) =>
    api.put<{ import_destinations: ImportDestination[] }>("/api/platform-collections/default", {
      platform, collection_id: collectionId,
    }),
  /** Every platform collection not linked yet becomes (or joins) a collection of the same name. */
  transferPlatforms: (body: { space_id?: number; parent_id?: number | null; platform?: string }) =>
    api.post<PlatformLinks>("/api/platform-collections/transfer", body),
  linkPlatform: (body: {
    platform: string;
    name: string;
    collection_id: number | null;
    mode: "auto" | "manual";
    create_collection?: boolean;
    space_id?: number;
    parent_id?: number | null;
  }) => api.put<PlatformLinks>("/api/platform-collections", body),
  applyPlatform: (platform: string, name: string) =>
    api.post<PlatformLinks>("/api/platform-collections/apply", { platform, name }),
  createCollection: (name: string, parentId: number | null = null, spaceId?: number) =>
    api.post<CollectionsOverview>("/api/collections", { name, parent_id: parentId, ...(spaceId ? { space_id: spaceId } : {}) }),
  /** Put your own picture on a collection (a data address from a chosen file). */
  uploadCollectionIcon: (id: number, data: string) => api.post<CollectionsOverview>(`/api/collections/${id}/icon`, { data }),
  changeCollection: (id: number, change: CollectionChange) =>
    api.patch<CollectionsOverview>(`/api/collections/${id}`, change),
  placeCollection: (id: number, parentId: number | null, index: number, spaceId?: number) =>
    api.post<CollectionsOverview>(`/api/collections/${id}/place`, {
      parent_id: parentId,
      index,
      ...(spaceId ? { space_id: spaceId } : {}),
    }),
  /** Move (inside a collection, or to the top of a space) or delete every picked collection. */
  bulkCollections: (body: { ids: number[]; action: "move" | "delete"; parent_id?: number | null; space_id?: number }) =>
    api.post<CollectionsOverview & { changed: number }>("/api/collections/bulk", body),
  createSpace: (name: string) => api.post<CollectionsOverview>("/api/spaces", { name }),
  changeSpace: (id: number, change: { name?: string; color?: string; clear_color?: boolean; index?: number }) =>
    api.patch<CollectionsOverview>(`/api/spaces/${id}`, change),
  deleteSpace: (id: number) => api.del<CollectionsOverview>(`/api/spaces/${id}`),
};

// ---------- "something changed" ----------

const CHANGED = "keptwise:organize-changed";

/** Tell every screen (and the sidebar) that collections or tags changed. */
export function announceChange(): void {
  window.dispatchEvent(new Event(CHANGED));
}

export function onOrganizeChange(listener: () => void): () => void {
  window.addEventListener(CHANGED, listener);
  return () => window.removeEventListener(CHANGED, listener);
}

// ---------- dragging ----------

/** Saves being dragged: one, or every selected one. */
export const ITEMS_DRAG = "application/x-saves-item";
export const COLLECTION_DRAG = "application/x-keptwise-collection";
export const NAV_DRAG = "application/x-keptwise-nav";

export type ItemsDrag = { itemId: number; fromId: number | null; itemIds?: number[] };

export function readItemsDrag(data: DataTransfer): ItemsDrag | null {
  const raw = data.getData(ITEMS_DRAG);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ItemsDrag;
  } catch {
    return null;
  }
}

/** Every save in a drag (a group when several were selected). */
export function draggedIds(drag: ItemsDrag): number[] {
  return drag.itemIds && drag.itemIds.length > 0 ? drag.itemIds : [drag.itemId];
}
