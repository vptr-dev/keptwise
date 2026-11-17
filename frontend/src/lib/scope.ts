// The platform picker (top left): look at All saves, or just TikTok,
// YouTube, ... The choice is kept by the backend, which narrows the
// Library, Collections, Tags, Unsave, search and the AI Assistant to it.
import { useCallback, useEffect, useState } from "react";

import { api } from "./api";

export type PlatformChoice = { id: string; label: string; count: number };
export type Scope = { platform: string | null; platforms: PlatformChoice[]; total: number };

// A small coloured mark for each platform (no logos, just its colour).
export const PLATFORM_DOTS: Record<string, string> = {
  tiktok: "bg-zinc-900 ring-1 ring-pink-400 dark:bg-zinc-100",
  youtube: "bg-red-600",
  instagram: "bg-gradient-to-br from-amber-400 via-pink-500 to-violet-600",
  facebook: "bg-blue-600",
};

export const scopeApi = {
  get: () => api.get<Scope>("/api/scope"),
  choose: (platform: string | null) => api.put<Scope>("/api/scope", { platform }),
};

// Keep only a well-formed answer, so an odd reply can't break the sidebar.
function tidy(raw: unknown): Scope {
  const data = (raw && typeof raw === "object" ? raw : {}) as Partial<Scope>;
  return {
    platform: typeof data.platform === "string" ? data.platform : null,
    platforms: Array.isArray(data.platforms) ? data.platforms : [],
    total: typeof data.total === "number" ? data.total : 0,
  };
}

export function useScope() {
  const [scope, setScope] = useState<Scope>({ platform: null, platforms: [], total: 0 });
  const reload = useCallback(() => {
    scopeApi.get().then((data) => setScope(tidy(data))).catch(() => undefined);
  }, []);
  useEffect(reload, [reload]);
  const choose = useCallback(async (platform: string | null) => {
    setScope((old) => ({ ...old, platform })); // show it straight away
    try {
      setScope(tidy(await scopeApi.choose(platform)));
    } catch {
      reload();
    }
  }, [reload]);
  return { scope, choose, reload };
}
