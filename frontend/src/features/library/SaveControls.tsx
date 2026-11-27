import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { icons } from "../../components/icons";
import { toast } from "../../components/Toasts";
import { Button } from "../../components/ui";
import { errorText } from "../../lib/api";
import { announceChange, organizeApi } from "../organize/organizeApi";
import { libraryApi, type LibraryItem } from "./libraryApi";

const archiveEvent = "keptwise-archive-changed";
function refreshArchive() {
  announceChange();
  window.dispatchEvent(new Event(archiveEvent));
}
export function onArchiveChange(listener: () => void) {
  window.addEventListener(archiveEvent, listener);
  return () => window.removeEventListener(archiveEvent, listener);
}

const Selection = createContext<{ ids: number[]; toggle(id: number): void } | null>(null);
const button = "inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/95 p-1.5 text-zinc-700 shadow ring-1 ring-black/10 hover:bg-indigo-100 dark:bg-zinc-900 dark:text-zinc-200";

export function RowSelection({ children }: { children: ReactNode }) {
  const [ids, setIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  function toggle(id: number) {
    if (!busy) setIds(old => old.includes(id) ? old.filter(value => value !== id) : [...old, id]);
  }
  async function archive() {
    setBusy(true);
    try {
      const result = await organizeApi.bulk({ action: "delete", item_ids: ids });
      setIds([]); refreshArchive(); toast("Archived " + result.changed + " saves. Use Undo to put them back.");
    } catch (e) { toast(errorText(e), { tone: "error" }); } finally { setBusy(false); }
  }
  return <Selection.Provider value={{ ids, toggle }}>{children}
    {ids.length > 0 && createPortal(<div role="toolbar" aria-label="Selected videos" className="fixed bottom-4 right-4 z-[120] flex items-center gap-3 rounded-xl bg-white p-3 text-sm shadow-lg dark:bg-zinc-900">
      <b>{ids.length} selected</b><Button size="sm" disabled={busy} onClick={archive}>Archive selected</Button>
      <Button variant="ghost" size="sm" disabled={busy} onClick={() => setIds([])}>Clear selection</Button>
    </div>, document.body)}
  </Selection.Provider>;
}

export function SaveControls({ id, title, archived, select = true, onChange }: {
  id: number; title: string; archived?: boolean; select?: boolean; onChange?: (item: LibraryItem) => void;
}) {
  const selection = useContext(Selection);
  const [busy, setBusy] = useState(false);
  const [edited, setEdited] = useState<{ original?: boolean; value: boolean }>();
  const inArchive = edited && edited.original === archived ? edited.value : !!archived;
  const picked = selection?.ids.includes(id);
  async function archive() {
    setBusy(true);
    try {
      const next = await libraryApi.patch(id, { deleted: !inArchive });
      setEdited({ original: archived, value: !!next.deleted });
      if (picked && next.deleted) selection?.toggle(id);
      onChange?.(next); refreshArchive();
      toast(inArchive ? "Restored from Archive." : "Moved to Archive. Use Undo to put it back.");
    } catch (e) { toast(errorText(e), { tone: "error" }); } finally { setBusy(false); }
  }
  return <span className={"inline-flex items-center gap-1 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100 " + (picked ? "opacity-100" : "opacity-0")}>
    {select && selection && !inArchive && <button type="button" className={button} aria-pressed={!!picked} aria-label={"Select " + title} title="Select video"
      onClick={e => { e.preventDefault(); e.stopPropagation(); selection.toggle(id); }}>{picked ? icons.check : icons.select}</button>}
    <button type="button" className={button} disabled={busy} title={inArchive ? "Restore from Archive" : "Archive video"}
      aria-label={(inArchive ? "Restore " : "Archive ") + title}
      onClick={e => { e.preventDefault(); e.stopPropagation(); void archive(); }}>{inArchive ? icons.back : icons.archive}</button>
  </span>;
}
