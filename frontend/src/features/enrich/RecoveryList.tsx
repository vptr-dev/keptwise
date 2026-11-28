import { useState } from "react";
import { Button, Notice } from "../../components/ui";
import { api, errorText } from "../../lib/api";
import type { RemainingVideo } from "../../lib/jobs";

type Page = { total: number; items: RemainingVideo[] };
export default function RecoveryList() {
  const [page, setPage] = useState<Page>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load(offset: number) {
    setBusy(true);
    setError("");
    try {
      const next = await api.get<Page>(`/api/enrich/problems?offset=${offset}`);
      setPage(old => ({total: next.total, items: offset && old ? [...old.items, ...next.items] : next.items}));
    } catch (error) {
      setError(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  return <details className="rounded-xl border border-zinc-200 p-3 text-sm dark:border-zinc-800"
    onToggle={event => { if (event.currentTarget.open && !busy) void load(0); }}>
    <summary className="cursor-pointer font-medium">Video problems</summary>
    {error && <Notice tone="error">{error}</Notice>}
    {busy && !page && <p className="mt-2 text-zinc-500">Loading…</p>}
    {page && (
      <div className="mt-2 space-y-2">
        <p className="text-zinc-500">{page.total ? `${page.total.toLocaleString()} videos with a recorded problem` : "No video problems recorded."}</p>
        <ul className="max-h-72 divide-y divide-zinc-200 overflow-auto dark:divide-zinc-800">
          {page.items.map(item => <li key={item.id} className="py-2">
            <a className="font-medium underline" href={`#/item/${item.id}`}>{item.title}</a>
            <p className="text-xs text-zinc-500">{item.unavailable ? "Unavailable on its platform. Open the save to check availability." : "Open the save to retry its transcript."}</p>
            {item.error && <p className="text-xs text-zinc-500">{item.error}</p>}
          </li>)}
        </ul>
        {page.items.length < page.total && <Button size="sm" variant="secondary" disabled={busy}
          onClick={() => void load(page.items.length)}>Show more problems</Button>}
      </div>
    )}
  </details>;
}
