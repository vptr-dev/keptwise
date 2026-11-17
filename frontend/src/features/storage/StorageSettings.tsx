// Settings -> Storage: what takes up space on this PC, and deleting it.
// Deleting a model never loses saves or notes: whatever needs it asks to
// download it again (or does so by itself next time).
import { useCallback, useEffect, useState } from "react";

import { Badge, Button, Card, Notice, formatBytes } from "../../components/ui";
import { api, errorText } from "../../lib/api";
import { announceChange } from "../organize/organizeApi";

export type StorageEntry = {
  id: string;
  group: string;
  label: string;
  bytes: number;
  note: string;
  can_delete: boolean;
  in_use: boolean;
};

type StorageList = {
  entries: StorageEntry[];
  data_folder: string;
  saves?: number; // how many saves there are to clear
  backups?: number; // database copies kept before updates
  backups_bytes?: number;
  cleared?: { saves?: number; backups?: number };
};
export type ClearWhat = "backups" | "saves" | "everything";

export const storageApi = {
  list: () => api.get<StorageList>("/api/storage"),
  remove: (id: string) => api.del<StorageList>(`/api/storage/${encodeURIComponent(id)}`),
  clear: (what: ClearWhat) => api.post<StorageList>("/api/storage/clear", { what }),
};

const GROUP_ORDER = ["AI models", "Speech to text", "Search", "Files"];

function EntryRow({
  entry,
  busy,
  onDelete,
}: {
  entry: StorageEntry;
  busy: boolean;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
            {entry.label}
            {entry.in_use && <Badge tone="indigo">In use</Badge>}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400">{entry.note}</p>
        </div>
        <span className="shrink-0 text-sm tabular-nums text-zinc-600 dark:text-zinc-300">{formatBytes(entry.bytes)}</span>
        {entry.can_delete && !confirming && (
          <Button size="sm" variant="secondary" disabled={busy || entry.bytes === 0} onClick={() => setConfirming(true)}>
            {entry.group === "Files" ? "Clear" : "Delete"}
          </Button>
        )}
      </div>
      {confirming && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900 dark:bg-red-950/50 dark:text-red-200">
          <span className="flex-1">
            Delete {entry.label} and free {formatBytes(entry.bytes)}? {entry.in_use ? entry.note : ""}
          </span>
          <Button size="sm" variant="danger" disabled={busy} onClick={() => { setConfirming(false); onDelete(); }}>
            Yes, delete
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setConfirming(false)}>
            Keep it
          </Button>
        </div>
      )}
    </li>
  );
}

export default function StorageSettings() {
  const [list, setList] = useState<StorageList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    storageApi.list().then(setList).catch((e) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);

  async function remove(entry: StorageEntry) {
    setBusyId(entry.id);
    setError(null);
    try {
      setList(await storageApi.remove(entry.id));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusyId(null);
    }
  }

  const entries = list?.entries ?? [];
  const total = entries.reduce((sum, e) => sum + e.bytes, 0);
  const groups = GROUP_ORDER.filter((g) => entries.some((e) => e.group === g));

  return (
    <Card>
      <div className="mb-1 flex items-center justify-between gap-3">
        <h2 className="text-lg font-medium">Storage</h2>
        {list && <span className="text-sm tabular-nums text-zinc-500 dark:text-zinc-400">{formatBytes(total)} in total</span>}
      </div>
      <p className="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
        What Keptwise keeps on this PC. Delete models you don't need to free space; your saves and notes are never
        touched, and anything that needs a deleted model offers to download it again.
      </p>
      {error && (
        <div className="mb-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {!list && !error && <Notice>Loading…</Notice>}
      {groups.map((group) => (
        <section key={group} className="mt-3">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">{group}</h3>
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {entries
              .filter((e) => e.group === group)
              .map((entry) => (
                <EntryRow key={entry.id} entry={entry} busy={busyId !== null} onDelete={() => void remove(entry)} />
              ))}
          </ul>
        </section>
      ))}
      {list && !entries.some((e) => e.group === "AI models") && (
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          AI models downloaded in Ollama show here while Ollama is running.
        </p>
      )}
      {list && <p className="mt-4 break-all text-xs text-zinc-400">Data folder: {list.data_folder}</p>}
      {list && <ClearMyData list={list} onCleared={setList} onError={setError} />}
    </Card>
  );
}

const CLEAR_CHOICES: { what: ClearWhat; title: string; about: string; sure: string }[] = [
  {
    what: "backups",
    title: "Clear backups",
    about: "The copies of your database the app keeps before it updates.",
    sure: "Delete every backup? If an update ever went wrong there would be no copy to go back to.",
  },
  {
    what: "saves",
    title: "Clear my saves",
    about: "Every save with its transcript, notes, pictures, collections, tags, plans and chats.",
    sure: "Delete all your saves, notes, collections, tags, plans and chats? This can't be undone.",
  },
  {
    what: "everything",
    title: "Clear everything",
    about: "Your saves, the backups and the log. Models and settings stay.",
    sure: "Delete all your saves and every backup of them? Nothing will be left to bring them back.",
  },
];

/** Deleting your own data for good: the backups, the saves, or both. */
function ClearMyData({ list, onCleared, onError }: { list: StorageList; onCleared: (list: StorageList) => void; onError: (text: string | null) => void }) {
  const [asking, setAsking] = useState<ClearWhat | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const saves = list.saves ?? 0;
  const backups = list.backups ?? 0;
  const has = (what: ClearWhat) => (what === "backups" ? backups > 0 : what === "saves" ? saves > 0 : saves > 0 || backups > 0);

  async function clear(what: ClearWhat) {
    setBusy(true);
    setAsking(null);
    setDone(null);
    onError(null);
    try {
      const next = await storageApi.clear(what);
      onCleared(next);
      const parts = [
        next.cleared?.saves !== undefined ? `${next.cleared.saves.toLocaleString()} save${next.cleared.saves === 1 ? "" : "s"}` : null,
        next.cleared?.backups !== undefined ? `${next.cleared.backups} backup${next.cleared.backups === 1 ? "" : "s"}` : null,
      ].filter(Boolean);
      setDone(`Deleted ${parts.join(" and ")}.`);
      announceChange(); // the sidebar numbers catch up
    } catch (e) {
      onError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-6 border-t border-zinc-100 pt-5 dark:border-zinc-800" aria-label="Clear my data">
      <h3 className="text-sm font-semibold">Clear my data</h3>
      <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
        You have {saves.toLocaleString()} save{saves === 1 ? "" : "s"} and {backups} backup{backups === 1 ? "" : "s"}
        {backups > 0 ? ` (${formatBytes(list.backups_bytes)})` : ""}. Clearing deletes for good; nothing is copied first.
      </p>
      {done && (
        <div className="mt-3">
          <Notice tone="success" onClose={() => setDone(null)}>{done}</Notice>
        </div>
      )}
      <ul className="mt-2 divide-y divide-zinc-100 dark:divide-zinc-800">
        {CLEAR_CHOICES.map((choice) => (
          <li key={choice.what} className="py-3">
            <div className="flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{choice.title}</p>
                <p className="text-xs text-zinc-500 dark:text-zinc-400">{choice.about}</p>
              </div>
              {asking !== choice.what && (
                <Button size="sm" variant="secondary" disabled={busy || !has(choice.what)} onClick={() => setAsking(choice.what)}>
                  {has(choice.what) ? "Clear…" : "Nothing to clear"}
                </Button>
              )}
            </div>
            {asking === choice.what && (
              <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900 dark:bg-red-950/50 dark:text-red-200">
                <span className="flex-1">{choice.sure}</span>
                <Button size="sm" variant="danger" disabled={busy} onClick={() => void clear(choice.what)}>
                  Yes, delete
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setAsking(null)}>
                  Keep it
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
