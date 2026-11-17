// Talking to the backend about search, the similar-search index, item
// details and chat.
import { api } from "../../lib/api";
import type { Job } from "../../lib/jobs";
import type { ItemCard } from "../sorting/sortingApi";

export type Segment = { text: string; hit: boolean };

export type Match = {
  part: "about" | "transcript" | "notes";
  label: string; // "Transcript"
  segments: Segment[];
  at_seconds: number | null; // roughly where in the video
};

export type SimilarMatch = {
  part: Match["part"];
  label: string;
  text: string;
  score: number;
  at_seconds: number | null;
};

export type SearchResult = {
  item: ItemCard;
  found_by: ("words" | "similar")[];
  words: string[];
  matches: Match[];
  similar: SimilarMatch | null;
};

export type SearchResponse = { query: string; results: SearchResult[]; similar_ready: boolean };

export type SearchMode = "both" | "words" | "captions" | "similar";

export type IndexStatus = {
  model_ready: boolean;
  model_bytes: number;
  items_with_text: number;
  waiting: number;
  job: Job | null;
};

export type ItemDetails = { item: ItemCard; transcript: string | null };

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type ChatSource = { number: number; item_id: number; item: ItemCard };

export type ChatReply = {
  found: boolean;
  answer: string;
  sources: ChatSource[];
  searched: string;
  model?: string;
};

export const searchApi = {
  search: (q: string, mode: SearchMode = "both", signal?: AbortSignal) =>
    api.get<SearchResponse>(`/api/search?${new URLSearchParams({ q, mode })}`, signal),
  status: () => api.get<IndexStatus>("/api/search/status"),
  startIndex: () => api.post<IndexStatus>("/api/search/index"),
  item: (id: number) => api.get<ItemDetails>(`/api/items/${id}`),
  chat: (messages: ChatTurn[], signal?: AbortSignal) => api.post<ChatReply>("/api/chat", { messages }, signal),
};

/** "about 1:20 in" */
export function whereIn(seconds: number | null): string | null {
  if (seconds == null) return null;
  const whole = Math.round(seconds);
  return `about ${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")} in`;
}

/** Split text into pieces, marking every place one of the words appears. */
export function markWords(text: string, words: string[]): Segment[] {
  const clean = words.map((w) => w.trim()).filter((w) => w.length > 1);
  if (clean.length === 0) return [{ text, hit: false }];
  const escaped = clean.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "gi");
  return text
    .split(pattern)
    .filter((piece) => piece !== "")
    .map((piece) => ({ text: piece, hit: clean.some((w) => w.toLowerCase() === piece.toLowerCase()) }));
}
