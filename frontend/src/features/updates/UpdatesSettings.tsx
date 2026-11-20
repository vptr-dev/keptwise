// Settings -> About and updates: the version, the update check's on/off
// switch, and a "Check now" button.
import { useState } from "react";

import { Button, Card, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { formatDate } from "../library/libraryApi";
import UpdateNow from "./UpdateNow";
import { updatesApi, type UpdateStatus } from "./updatesApi";

export default function UpdatesSettings({
  status,
  onChange,
}: {
  status: UpdateStatus | null;
  onChange: (status: UpdateStatus) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<UpdateStatus>) {
    setBusy(true);
    setError(null);
    try {
      onChange(await action());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h2 className="mb-1 text-lg font-medium">About and updates</h2>
      <p className="kw-tip mb-4 text-sm text-zinc-500 dark:text-zinc-400">
        {status ? `You have version ${status.current}.` : "Loading…"} Keptwise is open source and keeps
        everything on this computer.
      </p>
      <p className="kw-tip mb-4 text-sm text-zinc-500 dark:text-zinc-400">
        Some exports, including TikTok’s, only list folder names. Import can create those folders.
        Collection links place videos when the export says which folder they belong to.
      </p>
      {status && (
        <div className="space-y-3">
          <label className="flex cursor-pointer items-start gap-2.5 text-sm">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-indigo-600"
              checked={status.enabled}
              disabled={busy}
              onChange={(event) => void run(() => updatesApi.setEnabled(event.target.checked))}
            />
            <span>
              Check for a new version once a day
              <span className="kw-tip block text-xs text-zinc-500 dark:text-zinc-400">
                Asks GitHub for the newest version number. Nothing about you or your saves is sent, and nothing is
                downloaded until you press Update now.
              </span>
            </span>
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="secondary" size="sm" disabled={busy || !status.enabled} onClick={() => void run(updatesApi.checkNow)}>
              {busy ? "Checking…" : "Check now"}
            </Button>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {status.checked_at ? `Last checked ${formatDate(status.checked_at)}` : "Not checked yet"}
            </span>
          </div>
          {status.update_available ? (
            <UpdateNow status={status} place="settings" />
          ) : status.error ? (
            <Notice tone="warning">{status.error}</Notice>
          ) : status.latest ? (
            <p className="text-sm text-emerald-700 dark:text-emerald-300">You have the newest version.</p>
          ) : null}
          {error && <Notice tone="error">{error}</Notice>}
        </div>
      )}
      <div className="mt-5 space-y-1 border-t border-zinc-200 pt-4 dark:border-zinc-800">
        <a
          className="inline-flex rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:hover:bg-zinc-800"
          href="mailto:victor.petrov7811@gmail.com?subject=Keptwise%20feedback"
          target="_blank"
          rel="noreferrer"
        >
          Report feedback
        </a>
        <p className="kw-tip text-xs text-zinc-500 dark:text-zinc-400">
          Opens an email draft you can edit. Sending it shares your email address.
        </p>
      </div>
    </Card>
  );
}
