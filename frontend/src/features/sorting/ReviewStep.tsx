// Step 3 on the Transcripts page: the saves the AI wasn't sure where to
// file. Pick for it right here, so transcripts, notes and review all happen
// on one page. (The same list is on Collections -> Needs review.)
import { useCallback, useEffect, useState } from "react";

import { Button, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { isActive, onJobUpdate } from "../../lib/jobs";
import { announceChange, onOrganizeChange } from "../organize/organizeApi";
import ItemCard from "./ItemCard";
import ReviewActions from "./ReviewActions";
import { COLLECTION_LIMIT, sortingApi, type Collection, type ItemCard as Item } from "./sortingApi";

const SHOWN = 5;

export default function ReviewStep() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [room, setRoom] = useState(true);
  const [all, setAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    sortingApi.library({ type: "review" }).then(setItems).catch((e) => setError(errorText(e)));
    sortingApi
      .collections()
      .then((o) => {
        setCollections(o.collections);
        const first = o.spaces?.[0]?.id;
        setRoom(o.collections.filter((c) => c.space_id === first).length < (o.limit ?? COLLECTION_LIMIT));
      })
      .catch(() => undefined);
  }, []);
  useEffect(load, [load]);
  useEffect(() => onOrganizeChange(load), [load]);
  // New notes can add saves to review: refresh when a notes or sort job ends.
  useEffect(() => onJobUpdate((job) => (job.kind === "notes" || job.kind === "sort") && !isActive(job) && load()), [load]);

  async function act(task: () => Promise<unknown>) {
    setError(null);
    try {
      await task();
    } catch (e) {
      setError(errorText(e));
    }
    announceChange();
  }

  const count = items?.length ?? 0;
  const shown = all ? items ?? [] : (items ?? []).slice(0, SHOWN);
  return (
    <section className="space-y-3" aria-label="Needs review">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-medium">Needs review</h2>
        <span className={`rounded-full px-2 text-xs tabular-nums ${count ? "bg-amber-500 text-white" : "bg-zinc-100 text-zinc-500 dark:bg-zinc-800"}`}>{count}</span>
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          {count ? "The AI wasn't sure where these go. Pick for it." : items ? "Nothing to review: the AI was sure about everything so far." : "…"}
        </p>
      </div>
      {error && <Notice tone="error" onClose={() => setError(null)}>{error}</Notice>}
      {shown.length > 0 && (
        <ul className="space-y-3">
          {shown.map((item) => (
            <li key={item.id}>
              <ItemCard
                item={item}
                collections={collections}
                fromId={null}
                onMove={(toId) => act(() => sortingApi.move(item.id, null, toId))}
                onRemove={(collectionId) => act(() => sortingApi.removeFrom(item.id, collectionId))}
                onChange={(card) => setItems((old) => old?.map((o) => (o.id === card.id ? card : o)) ?? old)}
                actions={<ReviewActions item={item} room={room} onAccept={(choice) => act(() => sortingApi.accept(item.id, choice))} />}
              />
            </li>
          ))}
        </ul>
      )}
      {count > SHOWN && (
        <Button variant="secondary" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${count}`}
        </Button>
      )}
    </section>
  );
}
