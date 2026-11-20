// Talking to the backend about transcripts (the "enrich" step).
import { api } from "../../lib/api";
import type { Job } from "../../lib/jobs";

export type EnrichCounts = {
  total: number;
  waiting: number;
  done: number;
  failed: number; // page, media or audio couldn't be read
  no_speech: number; // the speech model returned an empty transcript
  gone?: number; // unavailable on the platform
  failed_reasons?: { text: string; count: number }[];
};

export type SpeechModel = {
  id: string;
  label: string;
  approx_bytes: number;
  hint: string;
  downloaded: boolean;
};

export type SpeechSettings = {
  model: string;
  device: "auto" | "cpu";
  models: SpeechModel[];
};

export type EnrichOverview = { counts: EnrichCounts; speech: SpeechSettings; tiktok_session?: boolean };
export type EnrichTarget = "waiting" | "failed" | "no_speech" | "unavailable";

export type RecentVideo = {
  id: number;
  platform: string;
  platform_name: string;
  url: string;
  title: string | null;
  author: string | null;
  duration_s: number | null;
  seconds: number | null;
  status: string;
  error: string | null;
  has_thumbnail: boolean;
  transcript_preview: string | null;
  transcript_chars: number | null;
  no_speech: boolean;
  language: string | null;
};

export type EnrichResult = {
  message: string;
  transcribed: number;
  no_speech: number;
  details_only: number;
  failed: number;
  later: number;
  model: string;
  device: "gpu" | "cpu" | null;
};

export const enrichApi = {
  overview: () => api.get<EnrichOverview>("/api/enrich"),
  recent: (limit = 12) => api.get<RecentVideo[]>(`/api/enrich/recent?limit=${limit}`),
  start: (count: number | null, which: EnrichTarget = "waiting", itemId?: number) =>
    api.post<Job>("/api/enrich/start", { count, which, item_id: itemId }),
  connectTikTok: (file: File) =>
    api.put<{ connected: boolean }>("/api/enrich/tiktok-session", file.slice(0, file.size, "application/octet-stream")),
  disconnectTikTok: () => api.del<{ connected: boolean }>("/api/enrich/tiktok-session"),
  saveSettings: (changes: Partial<Pick<SpeechSettings, "model" | "device">>) =>
    api.put<SpeechSettings>("/api/enrich/settings", changes),
};

/** "1:05" for 65 seconds; "1:02:03" for longer videos. */
export function formatDuration(seconds: number | null): string | null {
  if (seconds == null) return null;
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const secs = String(whole % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${minutes}:${secs}`;
}
