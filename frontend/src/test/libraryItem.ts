// A fake save for tests, with the user's progress fields.
import type { LibraryItem } from "../features/library/libraryApi";

export function libraryItem(overrides: Partial<LibraryItem> = {}): LibraryItem {
  return {
    id: 1,
    platform: "tiktok",
    platform_name: "TikTok",
    url: "https://www.tiktok.com/@x/video/1",
    author: null,
    duration_s: 61,
    status: "processed",
    has_thumbnail: false,
    title: "Easy tomato pasta",
    caption: null,
    summary: "A quick pasta with fresh tomatoes.",
    kind: "recipe",
    kind_label: "Recipe",
    facts: ["Serves 2"],
    steps: ["Buy tomatoes", "Boil pasta", "Mix and serve"],
    steps_checked: [false, false, false],
    tags: ["dinner"],
    needs_review: false,
    review_reason: null,
    suggestions: [],
    new_collection: null,
    error: null,
    collections: [{ id: 3, name: "Cooking", origin: "mine", source: "ai", confidence: 0.95 }],
    saved_at: "2026-03-12T10:00:00Z",
    platform_collection: null,
    done: false,
    started_at: null,
    safe_to_unsave: true,
    unsaved: false,
    ...overrides,
  };
}
