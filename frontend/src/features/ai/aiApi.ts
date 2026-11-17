// Calls for the AI part of Settings.
import { useCallback, useEffect, useState } from "react";

import { api } from "../../lib/api";
import type { Job } from "../../lib/jobs";

export type ProviderView = {
  id: string;
  label: string;
  kind: "local" | "cloud";
  needs_key: boolean;
  key_saved: boolean;
  key_hint: string | null;
  key_url: string;
  model: string;
  base_url: string;
  default_base_url: string;
};

export type AiOverview = {
  current: string;
  current_kind: "local" | "cloud";
  current_label: string;
  setup_done: boolean;
  providers: ProviderView[];
};

export type RecommendedModel = {
  name: string;
  label: string;
  size_gb: number;
  note: string;
  installed: boolean;
};

export type OllamaStatus = {
  base_url: string;
  running: boolean;
  version: string | null;
  installed: string[];
  error: string | null;
  download_page: string;
  default_model: string;
  free_bytes: number | null;
  recommended: RecommendedModel[];
};

export type TestResult = { ok: boolean; message: string; code?: string };

export const aiApi = {
  overview: () => api.get<AiOverview>("/api/ai"),
  setCurrent: (provider: string) => api.put<AiOverview>("/api/ai/current", { provider }),
  setModel: (id: string, model: string) => api.put<AiOverview>(`/api/ai/providers/${id}`, { model }),
  setBaseUrl: (id: string, base_url: string) => api.put<AiOverview>(`/api/ai/providers/${id}`, { base_url }),
  saveKey: (id: string, key: string) => api.put<AiOverview>(`/api/ai/providers/${id}/key`, { key }),
  removeKey: (id: string) => api.del<AiOverview>(`/api/ai/providers/${id}/key`),
  models: (id: string) => api.get<{ models: string[]; model: string }>(`/api/ai/providers/${id}/models`),
  test: (id: string) => api.post<TestResult>(`/api/ai/providers/${id}/test`),
  ollama: () => api.get<OllamaStatus>("/api/ai/ollama"),
  pull: (model: string) => api.post<Job>("/api/ai/ollama/pull", { model }),
  setupDone: () => api.post<AiOverview>("/api/ai/setup-done", { done: true }),
  ready: () => api.get<{ ready: boolean; message: string; code: string | null }>("/api/ai/ready"),
};

/** The AI overview, plus a way to replace it after a change. */
export function useAiOverview() {
  const [overview, setOverview] = useState<AiOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reload = useCallback(() => {
    aiApi
      .overview()
      .then((data) => {
        setOverview(data);
        setError(null);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)));
  }, []);
  useEffect(reload, [reload]);
  return { overview, setOverview, error, reload };
}
