// Sending dropped export files to the backend and starting the import.
//
// Steps: ask the backend for an upload id, copy each file into the app's
// data folder (PUT, one request per file, with a progress callback), then
// start the "import" background job. Files never leave this PC.
import { api, ApiError } from "../../lib/api";
import type { Job } from "../../lib/jobs";

export function importVideoLink(url: string, reimport = false) {
  return api.post<{ status: "added" | "already_had" | "deleted_before"; platform_name: string; url: string }>("/api/imports/link", reimport ? {url, reimport} : {url});
}

export type UploadInfo = {
  upload_id: string;
  wanted_names: string[];
  wanted_extensions: string[];
};

/** One file to send, with its path inside what was dropped. */
export type DroppedFile = { file: File; path: string };

export type PlatformResult = {
  platform: string;
  name: string;
  found: number;
  new: number;
  already_had: number;
  filed?: number;
  collections: string[];
  notes: string[];
};

export type ImportResult = {
  message: string;
  found: number;
  new: number;
  already_had: number;
  platforms: PlatformResult[];
};

export type LibrarySummary = {
  total: number;
  platforms: { platform: string; name: string; count: number }[];
};

export const NOTHING_TO_SEND =
  "None of these files look like a TikTok, YouTube, Instagram or Facebook export. Drop the zip file you downloaded, or its unzipped folder.";

export function getSummary(): Promise<LibrarySummary> {
  return api.get<LibrarySummary>("/api/imports/summary");
}

// ---------- reading what was dropped ----------

/** Files from a drop, including everything inside dropped folders. */
export async function filesFromDrop(data: DataTransfer): Promise<DroppedFile[]> {
  const entries = Array.from(data.items ?? [])
    .map((item) => (item.kind === "file" ? item.webkitGetAsEntry?.() : null))
    .filter((entry): entry is FileSystemEntry => !!entry);
  if (entries.length === 0) {
    return Array.from(data.files).map((file) => ({ file, path: file.name }));
  }
  const found: DroppedFile[] = [];
  for (const entry of entries) await walkEntry(entry, found);
  return found;
}

async function walkEntry(entry: FileSystemEntry, found: DroppedFile[]): Promise<void> {
  const path = entry.fullPath.replace(/^\/+/, "") || entry.name;
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) =>
      (entry as FileSystemFileEntry).file(resolve, reject),
    );
    found.push({ file, path });
    return;
  }
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  // readEntries gives at most ~100 entries per call, so keep asking.
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) =>
      reader.readEntries(resolve, reject),
    );
    if (batch.length === 0) break;
    for (const child of batch) await walkEntry(child, found);
  }
}

/** Files from the "Choose file" / "Choose folder" buttons. */
export function filesFromInput(list: FileList | null): DroppedFile[] {
  return Array.from(list ?? []).map((file) => ({
    file,
    path: file.webkitRelativePath || file.name,
  }));
}

/**
 * Which files to copy. A file dropped on its own is always sent. From a
 * folder, only the files the importers read (and zips/CSVs) are sent, so
 * photos, videos and messages are never copied.
 */
export function pickWanted(files: DroppedFile[], info: Pick<UploadInfo, "wanted_names" | "wanted_extensions">): DroppedFile[] {
  const names = new Set(info.wanted_names.map((name) => name.toLowerCase()));
  return files.filter(({ file, path }) => {
    if (!path.includes("/")) return true;
    const name = file.name.toLowerCase();
    return names.has(name) || info.wanted_extensions.some((ext) => name.endsWith(ext));
  });
}

/** A short name for what was dropped, e.g. "tiktok-export.zip". */
export function dropName(files: DroppedFile[]): string {
  if (files.length === 1) return files[0].path.split("/").pop() ?? "export";
  const tops = new Set(files.map((f) => f.path.split("/")[0]));
  if (tops.size === 1) return [...tops][0];
  return `${files.length} files`;
}

// ---------- sending ----------

export type Upload = {
  /** Resolves with the started import job. */
  done: Promise<Job>;
  /** Stops copying and throws away what was copied. */
  cancel: () => void;
};

export function startImport(
  files: DroppedFile[],
  onProgress: (sent: number, total: number) => void,
): Upload {
  let cancelled = false;
  let current: XMLHttpRequest | null = null;
  let uploadId: string | null = null;

  const done = (async () => {
    const info = await api.post<UploadInfo>("/api/imports");
    uploadId = info.upload_id;
    try {
      const chosen = pickWanted(files, info);
      if (chosen.length === 0) throw new Error(NOTHING_TO_SEND);
      const total = chosen.reduce((sum, { file }) => sum + file.size, 0);
      let sent = 0;
      onProgress(0, total);
      for (const dropped of chosen) {
        if (cancelled) throw new Error("Cancelled");
        await sendFile(info.upload_id, dropped, (bytes) => onProgress(sent + bytes, total), (xhr) => {
          current = xhr;
        });
        sent += dropped.file.size;
        onProgress(sent, total);
      }
      if (cancelled) throw new Error("Cancelled");
      return await api.post<Job>(`/api/imports/${info.upload_id}/start`, { name: dropName(files) });
    } catch (error) {
      api.del(`/api/imports/${info.upload_id}`).catch(() => undefined);
      throw error;
    }
  })();

  return {
    done,
    cancel: () => {
      cancelled = true;
      current?.abort();
      if (uploadId) api.del(`/api/imports/${uploadId}`).catch(() => undefined);
    },
  };
}

// XMLHttpRequest instead of fetch(), because only it reports upload progress.
function sendFile(
  uploadId: string,
  { file, path }: DroppedFile,
  onBytes: (bytes: number) => void,
  onStart: (xhr: XMLHttpRequest) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", `/api/imports/${uploadId}/files?path=${encodeURIComponent(path)}`);
    xhr.upload.onprogress = (event) => onBytes(event.loaded);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve();
      let message = `Copying ${file.name} failed (status ${xhr.status}).`;
      try {
        const data = JSON.parse(xhr.responseText) as { detail?: unknown };
        if (typeof data.detail === "string") message = data.detail;
      } catch {
        // not JSON; keep the generic message
      }
      reject(new ApiError(xhr.status, message));
    };
    xhr.onerror = () => reject(new Error(`Couldn't copy ${file.name}. Is the app still running?`));
    xhr.onabort = () => reject(new Error("Cancelled"));
    onStart(xhr);
    xhr.send(file);
  });
}
