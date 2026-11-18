// Plans (#/plans): your own lists to work through, like "Weekend in Lisbon"
// or "Meal prep this week". A plan holds saves and to-dos of your own, can be
// for a day, and finishes when everything is ticked. Pinned plans and the
// ones due soonest sit at the top.
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { useContextMenu } from "../components/ContextMenu";
import { useDialog } from "../components/Dialog";
import EmptyState from "../components/EmptyState";
import ProgressBar from "../components/ProgressBar";
import { toast } from "../components/Toasts";
import { icons } from "../components/icons";
import { Button, Card, Notice, Segmented, inputClass } from "../components/ui";
import { formatDate } from "../features/library/libraryApi";
import { NoPicture } from "../features/library/Thumb";
import { COLOR_DOTS, announceChange } from "../features/organize/organizeApi";
import { dueText, plansApi, type PlanSummary, type PlansList } from "../features/plans/plansApi";
import { sortingApi, type Collection } from "../features/sorting/sortingApi";
import { errorText } from "../lib/api";
import { navigate } from "../lib/router";
import { Tip } from "../lib/tips";

/** One press starts a plan with a name and a few to-dos to fill in. */
const STARTERS: { name: string; tasks: string[]; sections?: string[] }[] = [
  { name: "Weekend trip", tasks: ["Book where to stay", "Pack"], sections: ["Day 1", "Day 2"] },
  { name: "Meal prep this week", tasks: ["Write the shopping list", "Do the shopping"] },
  { name: "Workout plan", tasks: ["Pick the days"], sections: ["Monday", "Wednesday", "Friday"] },
  { name: "Things to make", tasks: ["Get what's needed"] },
];

type SortKey = "smart" | "due" | "name" | "updated";

function Preview({ plan }: { plan: PlanSummary }) {
  const tiles = plan.preview.slice(0, 4);
  return (
    <div className="grid h-20 w-20 shrink-0 grid-cols-2 gap-0.5 overflow-hidden rounded-xl bg-zinc-100 dark:bg-zinc-800">
      {tiles.map((tile) =>
        tile.has_thumbnail ? (
          <img key={tile.id} src={`/api/items/${tile.id}/thumbnail`} alt="" className="h-full w-full object-cover" loading="lazy" />
        ) : (
          <div key={tile.id} className="relative">
            <NoPicture small />
          </div>
        ),
      )}
      {tiles.length === 0 && <div className="col-span-2 row-span-2 flex items-center justify-center p-6 text-zinc-400">{icons.plans}</div>}
    </div>
  );
}

function PlanCard({ plan, onChange }: { plan: PlanSummary; onChange: () => void }) {
  const [openMenu, menu] = useContextMenu();
  const [ask, dialog] = useDialog();
  const total = plan.item_count + (plan.tasks_total ?? 0);
  const ticked = plan.items_done + (plan.tasks_done ?? 0);
  const due = dueText(plan.due_on, plan.done);
  const parts = [
    plan.item_count ? `${plan.item_count} save${plan.item_count === 1 ? "" : "s"}` : null,
    plan.tasks_total ? `${plan.tasks_total} to-do${plan.tasks_total === 1 ? "" : "s"}` : null,
  ].filter(Boolean);

  async function change(task: () => Promise<unknown>, message?: string) {
    try {
      await task();
      announceChange();
      if (message) toast(message);
      onChange();
    } catch (e) {
      toast(errorText(e), { tone: "error" });
    }
  }
  const menuItems = () => [
    { label: plan.pinned ? "Unpin" : "Pin to the top", icon: icons.pin, onSelect: () => void change(() => plansApi.change(plan.id, { pinned: !plan.pinned })) },
    { label: plan.done ? "Reopen" : "Mark finished", icon: icons.check, onSelect: () => void change(() => plansApi.change(plan.id, { done: !plan.done })) },
    { label: "Make a copy", icon: icons.plus, onSelect: () => void change(() => plansApi.copy(plan.id), `Copied “${plan.name}”.`) },
    { kind: "divider" as const },
    {
      label: "Delete…",
      icon: icons.trash,
      danger: true,
      onSelect: async () => {
        const sure = await ask.confirm({ title: `Delete “${plan.name}”?`, body: "Its saves stay in your library.", confirm: "Delete", danger: true });
        if (sure) void change(() => plansApi.remove(plan.id), `Deleted the plan “${plan.name}”.`);
      },
    },
  ];

  return (
    <div
      className={`group flex items-stretch rounded-2xl border bg-white shadow-sm transition hover:shadow-md dark:bg-zinc-900 ${
        due?.late ? "border-red-200 dark:border-red-900" : "border-zinc-200 hover:border-indigo-300 dark:border-zinc-800 dark:hover:border-indigo-700"
      }`}
      onContextMenu={(event) => openMenu(event, menuItems(), plan.name)}
      data-testid={`plan-${plan.id}`}
    >
      <a
        href={`#/plans/${plan.id}`}
        className="flex min-w-0 flex-1 items-center gap-4 rounded-2xl p-3 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500"
      >
        <Preview plan={plan} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {plan.color && <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${COLOR_DOTS[plan.color]}`} aria-hidden="true" />}
            <h3 className="truncate font-medium">{plan.name}</h3>
            {due && <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${due.tone}`}>{due.text}</span>}
            <span className="ml-auto shrink-0 text-xs text-zinc-500 dark:text-zinc-400">
              {plan.done ? `Finished ${formatDate(plan.done_at) ?? ""}` : `Updated ${formatDate(plan.updated_at) ?? ""}`}
            </span>
          </div>
          <p className="mt-0.5 truncate text-sm text-zinc-600 dark:text-zinc-400">
            {plan.note ||
              (total === 0
                ? "Empty. Add saves or to-dos to it."
                : plan.done
                  ? `All done · ${parts.join(" · ")}`
                  : `${total - ticked} of ${total} to go · ${parts.join(" · ")}`)}
          </p>
          {total > 0 && (
            <div className="mt-2 flex items-center gap-3">
              <ProgressBar done={ticked} total={total} label={`${plan.name} progress`} />
              <span className="shrink-0 text-xs tabular-nums text-zinc-500">
                {ticked}/{total}
                {plan.steps_total > 0 && ` · ${plan.steps_done}/${plan.steps_total} steps`}
              </span>
            </div>
          )}
        </div>
      </a>
      <div className="flex flex-col justify-center gap-1 pr-2">
        <button
          type="button"
          aria-label={plan.pinned ? `Unpin ${plan.name}` : `Pin ${plan.name}`}
          aria-pressed={plan.pinned}
          title={plan.pinned ? "Unpin" : "Pin to the top"}
          onClick={() => void change(() => plansApi.change(plan.id, { pinned: !plan.pinned }))}
          className={`h-7 w-7 rounded-md p-1.5 transition hover:bg-zinc-100 dark:hover:bg-zinc-800 ${
            plan.pinned ? "text-amber-500" : "text-zinc-300 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 dark:text-zinc-600"
          }`}
        >
          {icons.pin}
        </button>
        <button
          type="button"
          aria-label={`More for ${plan.name}`}
          onClick={(event) => openMenu(event, menuItems(), plan.name)}
          className="h-7 w-7 rounded-md p-1.5 text-zinc-400 opacity-0 transition hover:bg-zinc-100 group-hover:opacity-100 focus-visible:opacity-100 dark:hover:bg-zinc-800"
        >
          {icons.more}
        </button>
      </div>
      {menu}
      {dialog}
    </div>
  );
}

function sortPlans(list: PlanSummary[], key: SortKey): PlanSummary[] {
  const byDue = (a: PlanSummary, b: PlanSummary) => (a.due_on ?? "9999").localeCompare(b.due_on ?? "9999");
  const byUpdated = (a: PlanSummary, b: PlanSummary) => b.updated_at.localeCompare(a.updated_at);
  const sorted = [...list];
  if (key === "name") sorted.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
  else if (key === "updated") sorted.sort(byUpdated);
  else if (key === "due") sorted.sort((a, b) => byDue(a, b) || byUpdated(a, b));
  else sorted.sort((a, b) => Number(b.pinned) - Number(a.pinned) || byDue(a, b) || byUpdated(a, b));
  return sorted;
}

export default function PlansPage() {
  const [data, setData] = useState<PlansList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"open" | "finished">("open");
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");
  const [from, setFrom] = useState("");
  const [collections, setCollections] = useState<Collection[]>([]);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("smart");
  const [making, setMaking] = useState(false);

  const load = () => plansApi.list().then(setData).catch((e) => setError(errorText(e)));
  useEffect(() => {
    void load();
    sortingApi
      .collections()
      .then((o) => setCollections(o.collections.filter((c) => (c.total ?? c.count) > 0)))
      .catch(() => undefined);
  }, []);

  async function make(planName: string, extra: { note?: string; due_on?: string; collection_id?: number } = {}, starter?: (typeof STARTERS)[number]) {
    setError(null);
    setMaking(true);
    try {
      const { note: planNote, ...rest } = extra;
      const plan = await plansApi.create(planName, [], planNote, rest);
      if (starter) {
        for (const task of starter.tasks) await plansApi.addTask(plan.id, task);
        for (const section of starter.sections ?? []) await plansApi.addTask(plan.id, `Plan ${section.toLowerCase()}`, section);
      }
      announceChange();
      navigate(`/plans/${plan.id}`);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setMaking(false);
    }
  }

  function create(event: FormEvent) {
    event.preventDefault();
    const collection = collections.find((c) => String(c.id) === from);
    const planName = name.trim() || collection?.name;
    if (!planName) return;
    void make(planName, { note: note.trim() || undefined, due_on: due || undefined, collection_id: collection?.id });
  }

  const list = useMemo(() => {
    const words = search.trim().toLowerCase();
    const shown = (data?.plans ?? []).filter(
      (p) => (tab === "open" ? !p.done : p.done) && (!words || `${p.name} ${p.note ?? ""}`.toLowerCase().includes(words)),
    );
    return sortPlans(shown, sort);
  }, [data, tab, search, sort]);
  const late = (data?.plans ?? []).filter((p) => !p.done && dueText(p.due_on)?.late).length;
  const chosen = collections.find((c) => String(c.id) === from);

  return (
    <div className="mx-auto max-w-3xl space-y-5 px-8 py-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Plans</h1>
        <p className="kw-tip text-sm text-zinc-500 dark:text-zinc-400">
          Saves and to-dos to work through, for a day or whenever. Tick them off as you go.
        </p>
      </header>

      <Tip id="plans-how">
        Add saves to a plan from the Library: right-click a save, or pick several and use “Add to plan”. You can also start a
        plan from a whole collection below, and the AI Assistant can turn a plan into steps or a shopping list.
      </Tip>

      <Card>
        <form onSubmit={create} className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <input
              className={`${inputClass} min-w-48 flex-1`}
              placeholder={chosen ? chosen.name : "New plan, e.g. Weekend in Lisbon"}
              aria-label="New plan name"
              maxLength={80}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              type="date"
              aria-label="The day the new plan is for (optional)"
              title="The day it's for (optional)"
              className="rounded-lg border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              value={due}
              onChange={(e) => setDue(e.target.value)}
            />
            <Button type="submit" disabled={making || !(name.trim() || chosen)}>
              <span className="h-4 w-4">{icons.plus}</span>
              Make plan
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <input
              className={`${inputClass} min-w-48 flex-1`}
              placeholder="Note (optional)"
              aria-label="Note for the new plan"
              maxLength={500}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
            {collections.length > 0 && (
              <select
                aria-label="Start with the saves of a collection"
                className="max-w-64 rounded-lg border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
                value={from}
                onChange={(e) => setFrom(e.target.value)}
              >
                <option value="">Start empty</option>
                {collections.map((c) => (
                  <option key={c.id} value={c.id}>
                    From {c.path || c.name} ({(c.total ?? c.count).toLocaleString()})
                  </option>
                ))}
              </select>
            )}
          </div>
        </form>
        <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-zinc-100 pt-3 text-sm dark:border-zinc-800">
          <span className="text-xs text-zinc-500">Quick start:</span>
          {STARTERS.map((starter) => (
            <Button key={starter.name} size="sm" variant="ghost" disabled={making} onClick={() => void make(starter.name, {}, starter)}>
              {starter.name}
            </Button>
          ))}
        </div>
      </Card>

      {data && (
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            label="Which plans"
            value={tab}
            onChange={setTab}
            options={[
              { value: "open", label: `Open (${data.open})` },
              { value: "finished", label: `Finished (${data.finished})` },
            ]}
          />
          {late > 0 && tab === "open" && (
            <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800 dark:bg-red-900/60 dark:text-red-200">
              {late} late
            </span>
          )}
          <div className="ml-auto flex gap-2">
            {data.plans.length > 3 && (
              <input
                className={`${inputClass} !w-44 py-1.5`}
                placeholder="Find a plan"
                aria-label="Find a plan"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            )}
            <select
              aria-label="Sort plans"
              className="rounded-lg border border-zinc-300 bg-white px-2 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
            >
              <option value="smart">Pinned, then soonest</option>
              <option value="due">By day</option>
              <option value="updated">Last changed</option>
              <option value="name">By name</option>
            </select>
          </div>
        </div>
      )}
      <div className="space-y-3">
        {error && <Notice tone="error" onClose={() => setError(null)}>{error}</Notice>}
        {!data && !error && <Notice>Loading…</Notice>}
        {data && list.length === 0 &&
          (search.trim() ? (
            <p className="text-sm text-zinc-500">No plan matches “{search.trim()}”.</p>
          ) : tab === "open" ? (
            <EmptyState
              icon={icons.plans}
              title="No plans yet"
              action={<Button onClick={() => navigate("/library?status=processed")}>Find something to plan</Button>}
            >
              Make a plan above, start from a collection, or add saves to one straight from the Library.
            </EmptyState>
          ) : (
            <EmptyState icon={icons.check} title="Nothing finished yet">
              When everything in a plan is ticked off, it moves here.
            </EmptyState>
          ))}
        {list.map((plan) => (
          <PlanCard key={plan.id} plan={plan} onChange={() => void load()} />
        ))}
      </div>
    </div>
  );
}
