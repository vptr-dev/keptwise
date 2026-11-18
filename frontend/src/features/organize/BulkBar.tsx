// The bar at the bottom of the Library while saves are selected: put them
// all in a collection, move them, tag or untag them, add them to a plan,
// let the AI tag or sort them, or mark them done.
import { useEffect, useState } from "react";

import { toast } from "../../components/Toasts";
import { Button } from "../../components/ui";
import { errorText } from "../../lib/api";
import { navigate } from "../../lib/router";
import { plansApi, type PlanSummary } from "../plans/plansApi";
import { COLLECTIONS_PER_SAVE, sortingApi, type Collection } from "../sorting/sortingApi";
import { TAGS_PER_SAVE, announceChange, organizeApi, type BulkBody } from "./organizeApi";

const selectClass =
  "rounded-lg border border-zinc-300 bg-white px-2 py-1 text-xs text-zinc-800 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export default function BulkBar({
  ids,
  shownIn,
  onDone,
  onClear,
  onSelectAll,
  allSelected,
}: {
  ids: number[];
  shownIn: number | null; // the collection the Library is filtered to, if any
  onDone: () => void; // reload the grid
  onClear: () => void;
  onSelectAll: () => void;
  allSelected: boolean;
}) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [tag, setTag] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [plans, setPlans] = useState<PlanSummary[]>([]);

  useEffect(() => {
    sortingApi.collections().then((o) => setCollections(o.collections)).catch(() => undefined);
    plansApi.list().then((l) => setPlans(l.plans.filter((p) => !p.done))).catch(() => undefined);
  }, []);

  async function newPlan() {
    const name = window.prompt("Name of the new plan", "My plan");
    if (!name?.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const plan = await plansApi.create(name.trim(), ids);
      announceChange();
      navigate(`/plans/${plan.id}`);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  async function run(body: Omit<BulkBody, "item_ids">, done: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await organizeApi.bulk({ ...body, item_ids: ids });
      const what = body.action === "add_tag" ? `${TAGS_PER_SAVE} tags` : `${COLLECTIONS_PER_SAVE} collections`;
      const full = result.skipped_full ? ` ${result.skipped_full} skipped: they already had ${what}.` : "";
      setMessage(`${done} ${result.changed.toLocaleString()} save${result.changed === 1 ? "" : "s"}.${full}`);
      announceChange();
      onDone();
      return true;
    } catch (e) {
      setError(errorText(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  function tagSubmit(event: { preventDefault: () => void }, action: "add_tag" | "remove_tag") {
    event.preventDefault();
    if (!tag.trim()) return;
    void run({ action, tag: tag.trim().replace(/^#/, "") }, action === "add_tag" ? "Tagged" : "Untagged");
    setTag("");
  }

  const options = collections.map((c) => (
    <option key={c.id} value={c.id}>
      {c.name}
    </option>
  ));
  const shownName = collections.find((c) => c.id === shownIn)?.name;

  return (
    <div
      role="toolbar"
      aria-label="Selected saves"
      className="sticky bottom-4 z-20 mx-auto mt-6 flex max-w-5xl flex-wrap items-center gap-2 rounded-2xl border border-zinc-200 bg-white/95 px-4 py-3 text-sm shadow-lg backdrop-blur dark:border-zinc-700 dark:bg-zinc-900/95"
    >
      <span className="font-medium">{ids.length.toLocaleString()} selected</span>
      <Button size="sm" variant="ghost" onClick={allSelected ? onClear : onSelectAll}>
        {allSelected ? "Select none" : "Select all shown"}
      </Button>
      <span className="mx-1 h-5 w-px bg-zinc-200 dark:bg-zinc-700" aria-hidden="true" />
      <select
        aria-label="Add the selected saves to a collection"
        className={selectClass}
        value=""
        disabled={busy || ids.length === 0}
        onChange={(e) => e.target.value && void run({ action: "add_to", collection_id: Number(e.target.value) }, "Added")}
      >
        <option value="">Add to…</option>
        {options}
      </select>
      {shownIn !== null && (
        <>
          <select
            aria-label="Move the selected saves to another collection"
            className={selectClass}
            value=""
            disabled={busy || ids.length === 0}
            onChange={(e) =>
              e.target.value && void run({ action: "move_to", from_id: shownIn, collection_id: Number(e.target.value) }, "Moved")
            }
          >
            <option value="">Move to…</option>
            {options}
          </select>
          <Button size="sm" variant="ghost" disabled={busy || ids.length === 0} onClick={() => void run({ action: "remove_from", collection_id: shownIn }, "Took out")}>
            Take out of {shownName ?? "this collection"}
          </Button>
        </>
      )}
      <form className="flex items-center gap-1" onSubmit={(e) => tagSubmit(e, "add_tag")}>
        <input
          value={tag}
          maxLength={40}
          onChange={(e) => setTag(e.target.value)}
          placeholder="tag"
          aria-label="Tag for the selected saves"
          className="w-24 rounded-lg border border-zinc-300 bg-white px-2 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-950"
        />
        <Button size="sm" variant="secondary" type="submit" disabled={busy || !tag.trim() || ids.length === 0}>
          Add tag
        </Button>
        <Button size="sm" variant="ghost" disabled={busy || !tag.trim() || ids.length === 0} onClick={(e) => tagSubmit(e, "remove_tag")}>
          Remove tag
        </Button>
      </form>
      <select
        aria-label="Add the selected saves to a plan"
        className={selectClass}
        value=""
        disabled={busy || ids.length === 0}
        onChange={(e) => {
          if (e.target.value === "new") void newPlan();
          else if (e.target.value) void run({ action: "add_to_plan", plan_id: Number(e.target.value) }, "Added to the plan:");
        }}
      >
        <option value="">Add to plan…</option>
        {plans.map((plan) => (
          <option key={plan.id} value={plan.id}>
            {plan.name}
          </option>
        ))}
        <option value="new">New plan with these…</option>
      </select>
      <Button
        size="sm"
        variant="ghost"
        disabled={busy || ids.length === 0 || ids.length > 30}
        onClick={() => navigate(`/chat?items=${ids.join(",")}`)}
        title={ids.length > 30 ? "Pick 30 saves or fewer to ask about them" : "Bring these saves into a chat with the AI Assistant"}
      >
        Ask AI
      </Button>
      <Button
        size="sm"
        variant="danger"
        disabled={busy || ids.length === 0}
        title="They move to the Archive, where you can put them back"
        onClick={() => {
          const gone = ids;
          void run({ action: "delete" }, "Deleted").then((ok) => {
            if (!ok) return;
            toast(`Deleted ${gone.length} save${gone.length === 1 ? "" : "s"}. ${gone.length === 1 ? "It's" : "They're"} in the Archive.`, {
              undo: () => organizeApi.bulk({ item_ids: gone, action: "restore" }).then(() => { announceChange(); onDone(); }),
            });
            onClear();
          });
        }}
      >
        Delete
      </Button>
      <Button size="sm" variant="secondary" className="ml-auto" onClick={onClear}>
        Done selecting
      </Button>
      {(message || error) && (
        <p className={`w-full text-xs ${error ? "text-red-600 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400"}`} role="status">
          {error ?? message}
        </p>
      )}
    </div>
  );
}
