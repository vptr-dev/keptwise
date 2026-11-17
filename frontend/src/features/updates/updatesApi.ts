// The update check asks GitHub (at most once a day) whether a newer version
// exists. "Update now" (install) downloads, checks and installs it as a job.
import { api } from "../../lib/api";
import type { Job } from "../../lib/jobs";

export type UpdateStatus = {
  enabled: boolean;
  current: string;
  latest: string | null;
  update_available: boolean;
  url: string;
  checked_at: string | null;
  error: string | null;
  can_install?: boolean; // only the installed app can update itself
};

export const updatesApi = {
  status: () => api.get<UpdateStatus>("/api/updates"),
  checkNow: () => api.post<UpdateStatus>("/api/updates/check"),
  setEnabled: (enabled: boolean) => api.put<UpdateStatus>("/api/updates", { enabled }),
  install: () => api.post<Job>("/api/updates/install"),
};
