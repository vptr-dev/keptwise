import { useState } from "react";
import { Button, Notice, inputClass } from "../../components/ui";
import { errorText } from "../../lib/api";

type Preview = { saves: number; collections: number };
type DesktopBackup = {
  save_library_backup(): Promise<boolean>;
  preview_library_backup(): Promise<Preview | null>;
  restore_library_backup(name: string): Promise<void>;
};

export default function LibraryBackup() {
  const desktop = (window as Window & { pywebview?: { api?: DesktopBackup } }).pywebview?.api;
  const [preview, setPreview] = useState<Preview | null>(null);
  const [name, setName] = useState("Restored library");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  async function run(task: () => Promise<void>) {
    setBusy(true);
    setMessage(null);
    try {
      await task();
    } catch (error) {
      setMessage({ text: errorText(error), failed: true });
    } finally {
      setBusy(false);
    }
  }
  return <section className="mt-5 space-y-3 border-t border-zinc-200 pt-4 dark:border-zinc-700">
    <h3 className="font-medium">Library backup</h3>
    <p className="text-sm text-zinc-500">Save your library, notes, organisation and pictures to a ZIP file. Restore a copy in a new workspace.</p>
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="secondary" disabled={busy || !desktop?.save_library_backup} onClick={() => run(async () => {
        if (await desktop!.save_library_backup()) setMessage({text: "Library backup saved.", failed: false});
      })}>Save backup</Button>
      <Button size="sm" variant="secondary" disabled={busy || !desktop?.preview_library_backup} onClick={() => run(async () => {
        setPreview(null);
        setPreview(await desktop!.preview_library_backup());
      })}>Choose backup to restore</Button>
    </div>
    {preview && <form className="space-y-2" onSubmit={event => {
      event.preventDefault();
      void run(async () => {
        await desktop!.restore_library_backup(name.trim());
        window.dispatchEvent(new Event("keptwise-workspaces-changed"));
        setPreview(null);
        setMessage({text: "Restored as a new workspace. Open it in Settings → Workspaces.", failed: false});
      });
    }}>
      <p className="text-sm">Verified {preview.saves.toLocaleString()} saves and {preview.collections.toLocaleString()} collections. Your current workspace stays available.</p>
      <div className="flex flex-wrap gap-2">
        <input className={inputClass + " max-w-xs"} aria-label="Restored workspace name" maxLength={60}
          value={name} onChange={event => setName(event.target.value)} />
        <Button type="submit" size="sm" disabled={busy || !name.trim()}>Restore to new workspace</Button>
        <Button size="sm" variant="ghost" disabled={busy} onClick={() => setPreview(null)}>Cancel</Button>
      </div>
    </form>}
    {message && <Notice tone={message.failed ? "error" : "success"}>{message.text}</Notice>}
  </section>;
}
