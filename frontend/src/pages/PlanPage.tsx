// One plan (#/plans/12). A plan is for a day (optional), split into sections
// like "Day 1" or "To buy", and holds saves and to-dos of your own. Tick
// things off as you go; a save's steps tick inside it. Each save can carry a
// note for this plan. "All steps" shows every step of every save as one
// checklist. Right-click a save for everything else.
import { useEffect, useState, type FormEvent } from "react";

import { useContextMenu, type MenuItem } from "../components/ContextMenu";
import { useDialog, type Ask } from "../components/Dialog";
import ProgressBar from "../components/ProgressBar";
import { toast } from "../components/Toasts";
import { icons } from "../components/icons";
import { Button, Notice, Segmented, inputClass } from "../components/ui";
import { displayTitle, libraryApi, stepProgress, DEFAULT_QUERY, type LibraryItem } from "../features/library/libraryApi";
import { saveMenuItems } from "../features/library/saveMenu";
import StepsChecklist from "../features/library/StepsChecklist";
import Thumb from "../features/library/Thumb";
import { COLOR_DOTS, announceChange } from "../features/organize/organizeApi";
import { dueText, plansApi, type PlanDetails, type PlanEntry, type PlanTask } from "../features/plans/plansApi";
import { errorText } from "../lib/api";
import { navigate } from "../lib/router";

type ViewMode = "saves" | "steps";

export default function PlanPage({ planId }: { planId: number }) {
  const [plan, setPlan] = useState<PlanDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hideDone, setHideDone] = useState(false);
  const [mode, setMode] = useState<ViewMode>("saves");
  const [ask, dialog] = useDialog();
  const [openMenu, menu] = useContextMenu();

  useEffect(() => {
    plansApi
      .get(planId)
      .then((p) => {
        setPlan(p);
        setNote(p.note ?? "");
      })
      .catch((e) => {
        if ((e as { status?: number }).status === 404) setMissing(true);
        else setError(errorText(e));
      });
  }, [planId]);

  async function act(task: () => Promise<PlanDetails>) {
    setError(null);
    setBusy(true);
    try {
      const next = await task();
      setPlan(next);
      announceChange();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  if (missing) {
    return (
      <div className="mx-auto max-w-3xl px-8 py-8">
        <Notice tone="warning">That plan doesn't exist any more.</Notice>
        <Button className="mt-4" variant="secondary" onClick={() => navigate("/plans")}>
          Back to Plans
        </Button>
      </div>
    );
  }
  if (!plan) {
    return <div className="mx-auto max-w-3xl px-8 py-8">{error ? <Notice tone="error">{error}</Notice> : <Notice>Loading…</Notice>}</div>;
  }

  const ids = plan.items.map((e) => e.item.id);
  const move = (index: number, delta: number) => {
    const order = [...ids];
    const [moved] = order.splice(index, 1);
    order.splice(index + delta, 0, moved);
    void act(() => plansApi.reorder(plan.id, order));
  };
  const tool = (id: string) => navigate(`/chat?tool=${id}&plan=${plan.id}`);
  const sections = plan.sections ?? [];
  const tasks = plan.tasks ?? [];
  const total = plan.item_count + (plan.tasks_total ?? 0);
  const ticked = plan.items_done + (plan.tasks_done ?? 0);
  const due = dueText(plan.due_on, plan.done);

  function rename(event: FormEvent) {
    event.preventDefault();
    setEditing(false);
    if (name.trim() && name.trim() !== plan?.name) void act(() => plansApi.change(planId, { name: name.trim() }));
  }

  /** Put a save or a to-do in a section: an existing one, a new one, or none. */
  async function chooseSection(current: string | null, apply: (section: string | null) => Promise<PlanDetails>) {
    const NEW = "\u0000new";
    const picked = await ask.pick({
      title: "Move to a section",
      label: "Section",
      options: [
        { value: "", label: "No section" },
        ...sections.map((s) => ({ value: s, label: s })),
        { value: NEW, label: "New section…" },
      ].filter((o) => o.value !== (current ?? "") || o.value === NEW),
      confirm: "Move",
    });
    if (picked === null) return;
    let section: string | null = picked || null;
    if (picked === NEW) {
      section = await ask.text({ title: "New section", label: "Name, like Day 1 or To buy", confirm: "Add", maxLength: 40 });
      if (!section) return;
    }
    void act(() => apply(section));
  }

  async function newSection() {
    const section = await ask.text({ title: "New section", label: "Name, like Day 1 or To buy", confirm: "Add", maxLength: 40 });
    if (!section) return;
    const first = await ask.text({ title: `First to-do in “${section}”`, label: "What needs doing? (You can move saves here afterwards.)", confirm: "Add" });
    if (first) void act(() => plansApi.addTask(plan!.id, first, section));
  }

  async function removePlan() {
    const sure = await ask.confirm({ title: `Delete “${plan!.name}”?`, body: "Its saves stay in your library. The plan's to-dos and notes go.", confirm: "Delete", danger: true });
    if (!sure) return;
    await plansApi.remove(plan!.id);
    announceChange();
    toast(`Deleted the plan “${plan!.name}”.`);
    navigate("/plans");
  }

  const groups: { section: string | null; entries: PlanEntry[]; tasks: PlanTask[] }[] = [null, ...sections].map((section) => ({
    section,
    entries: plan.items.filter((e) => (e.section ?? null) === section && (!hideDone || !e.done)),
    tasks: tasks.filter((t) => (t.section ?? null) === section && (!hideDone || !t.done)),
  }));

  return (
    <div className="mx-auto max-w-3xl space-y-5 px-8 py-8">
      <a href="#/plans" className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200">
        <span className="h-4 w-4">{icons.back}</span>
        Plans
      </a>
      <header className="space-y-3">
        {editing ? (
          <form onSubmit={rename} className="flex gap-2">
            <input className={inputClass} aria-label="Plan name" autoFocus maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
            <Button type="submit">Save</Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
          </form>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            {plan.color && <span className={`h-3 w-3 rounded-full ${COLOR_DOTS[plan.color]}`} aria-hidden="true" />}
            <h1 className="text-2xl font-semibold tracking-tight">{plan.name}</h1>
            {plan.done && <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200">Finished</span>}
            {due && <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${due.tone}`}>{due.text}</span>}
            <div className="ml-auto flex flex-wrap gap-1">
              <Button size="sm" variant="ghost" aria-pressed={plan.pinned} onClick={() => act(() => plansApi.change(plan.id, { pinned: !plan.pinned }))} title="Pinned plans stay at the top of the list">
                {plan.pinned ? "Unpin" : "Pin"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => act(() => plansApi.change(plan.id, { done: !plan.done }))}>
                {plan.done ? "Reopen" : "Mark finished"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                aria-label="More for this plan"
                onClick={(event) =>
                  openMenu(event, [
                    { label: "Rename…", icon: icons.pencil, onSelect: () => { setName(plan.name); setEditing(true); } },
                    { kind: "colors", label: "Colour", value: plan.color, onPick: (color) => void act(() => plansApi.change(plan.id, { color: color ?? "accent" })) },
                    {
                      label: "Make a copy",
                      icon: icons.plus,
                      onSelect: async () => {
                        const copy = await plansApi.copy(plan.id);
                        announceChange();
                        toast("Copied. Nothing is ticked in the copy.");
                        navigate(`/plans/${copy.id}`);
                      },
                    },
                    { kind: "divider" },
                    { label: "Delete…", icon: icons.trash, danger: true, onSelect: () => void removePlan() },
                  ], plan.name)
                }
              >
                <span className="h-4 w-4">{icons.more}</span>
              </Button>
            </div>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <label className="flex items-center gap-2 text-zinc-600 dark:text-zinc-400">
            For
            <input
              type="date"
              aria-label="The day this plan is for"
              className="rounded-lg border border-zinc-300 bg-white px-2 py-1 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              value={plan.due_on ?? ""}
              onChange={(e) => void act(() => plansApi.change(plan.id, { due_on: e.target.value || null }))}
            />
          </label>
          {plan.due_on && (
            <button type="button" className="text-xs text-zinc-500 underline" onClick={() => void act(() => plansApi.change(plan.id, { due_on: null }))}>
              No day
            </button>
          )}
        </div>
        <textarea
          className={`${inputClass} min-h-12`}
          placeholder="A note for this plan: when, where, who with…"
          aria-label="Plan note"
          maxLength={500}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => note.trim() !== (plan.note ?? "") && act(() => plansApi.change(plan.id, { note: note.trim() || null }))}
        />
        {total > 0 && (
          <div className="flex items-center gap-3">
            <ProgressBar done={ticked} total={total} label="Done" />
            <span className="shrink-0 text-sm tabular-nums text-zinc-500">
              {ticked} of {total} done
              {plan.steps_total > 0 && ` · ${plan.steps_done}/${plan.steps_total} steps`}
            </span>
          </div>
        )}
      </header>

      {error && <Notice tone="error" onClose={() => setError(null)}>{error}</Notice>}

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => setAdding(!adding)} variant={adding ? "secondary" : "primary"}>
          <span className="h-4 w-4">{adding ? icons.close : icons.plus}</span>
          {adding ? "Done adding" : "Add saves"}
        </Button>
        <Button variant="secondary" onClick={() => void newSection()}>
          New section
        </Button>
        {plan.steps_total > 0 && (
          <Segmented
            label="How to show the plan"
            value={mode}
            onChange={setMode}
            options={[
              { value: "saves", label: "By save" },
              { value: "steps", label: "All steps" },
            ]}
          />
        )}
        {ticked > 0 && (
          <label className="flex items-center gap-1.5 text-sm text-zinc-600 dark:text-zinc-400">
            <input type="checkbox" checked={hideDone} onChange={(e) => setHideDone(e.target.checked)} />
            Hide done
          </label>
        )}
        {plan.item_count > 0 && (
          <div className="ml-auto flex flex-wrap items-center gap-1.5 text-sm">
            <span className="h-4 w-4 text-indigo-500">{icons.sparkle}</span>
            <Button size="sm" variant="ghost" onClick={() => tool("plan")}>Step-by-step plan</Button>
            <Button size="sm" variant="ghost" onClick={() => tool("shopping")}>Shopping list</Button>
            <Button size="sm" variant="ghost" onClick={() => tool("takeaways")}>Takeaways</Button>
          </div>
        )}
      </div>

      {adding && <AddSaves planIds={ids} onAdd={(itemIds) => act(() => plansApi.add(plan.id, itemIds))} />}

      {total === 0 && !adding && (
        <p className="rounded-2xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
          This plan is empty. Press “Add saves”, add a to-do below, or add saves from the Library.
        </p>
      )}

      {mode === "steps" ? (
        <AllSteps plan={plan} onItem={(item) => setPlan((old) => old && { ...old, items: old.items.map((e) => (e.item.id === item.id ? { ...e, item } : e)) })} />
      ) : (
        groups.map((group) => (
          <section key={group.section ?? ""} className="space-y-3" aria-label={group.section ?? "Not in a section"}>
            {group.section && (
              <div className="flex items-center gap-2 pt-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">{group.section}</h2>
                <span className="h-px flex-1 bg-zinc-200 dark:bg-zinc-800" />
                <button
                  type="button"
                  aria-label={`More for the section ${group.section}`}
                  className="h-6 w-6 rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800"
                  onClick={(event) =>
                    openMenu(event, [
                      {
                        label: "Rename…",
                        icon: icons.pencil,
                        onSelect: async () => {
                          const next = await ask.text({ title: "Rename section", label: "Name", value: group.section ?? "", maxLength: 40 });
                          if (next && next !== group.section) void act(() => plansApi.renameSection(plan.id, group.section!, next));
                        },
                      },
                      { label: "Remove the section (keep what's in it)", icon: icons.close, onSelect: () => void act(() => plansApi.renameSection(plan.id, group.section!, null)) },
                    ], group.section ?? undefined)
                  }
                >
                  {icons.more}
                </button>
              </div>
            )}
            <ol className="space-y-3" aria-label={group.section ? `Saves in ${group.section}` : "Saves in this plan"}>
              {group.entries.map((entry) => {
                const index = ids.indexOf(entry.item.id);
                return (
                  <EntryRow
                    key={entry.item.id}
                    entry={entry}
                    busy={busy}
                    first={index === 0}
                    last={index === ids.length - 1}
                    ask={ask}
                    onTick={(done) => act(() => plansApi.tick(plan.id, entry.item.id, done))}
                    onUp={() => move(index, -1)}
                    onDown={() => move(index, 1)}
                    onSection={() => void chooseSection(entry.section ?? null, (section) => plansApi.changeItem(plan.id, entry.item.id, { section }))}
                    onNote={(text) => act(() => plansApi.changeItem(plan.id, entry.item.id, { note: text }))}
                    onRemove={() =>
                      act(async () => {
                        const next = await plansApi.removeItem(plan.id, entry.item.id);
                        toast(`Taken out of “${plan.name}”.`, { undo: () => plansApi.add(plan.id, [entry.item.id]).then(setPlan) });
                        return next;
                      })
                    }
                    onItem={(item) => setPlan((old) => old && { ...old, items: old.items.map((e) => (e.item.id === item.id ? { ...e, item } : e)) })}
                  />
                );
              })}
            </ol>
            <ul className="space-y-1.5" aria-label={group.section ? `To-dos in ${group.section}` : "To-dos"}>
              {group.tasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  busy={busy}
                  onTick={(done) => act(() => plansApi.changeTask(plan.id, task.id, { done }))}
                  onText={(text) => act(() => plansApi.changeTask(plan.id, task.id, { text }))}
                  onSection={() => void chooseSection(task.section ?? null, (section) => plansApi.changeTask(plan.id, task.id, { section }))}
                  onRemove={() => act(() => plansApi.removeTask(plan.id, task.id))}
                />
              ))}
            </ul>
            <AddTask section={group.section} onAdd={(text) => act(() => plansApi.addTask(plan.id, text, group.section))} />
          </section>
        ))
      )}
      {menu}
      {dialog}
    </div>
  );
}

/** A to-do of your own: tick it, click its words to change them. */
function TaskRow({
  task,
  busy,
  onTick,
  onText,
  onSection,
  onRemove,
}: {
  task: PlanTask;
  busy: boolean;
  onTick: (done: boolean) => void;
  onText: (text: string) => void;
  onSection: () => void;
  onRemove: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(task.text);
  return (
    <li className="group flex items-center gap-3 rounded-xl border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900" data-testid={`task-${task.id}`}>
      <button
        type="button"
        role="checkbox"
        aria-checked={task.done}
        aria-label={`${task.text} done`}
        disabled={busy}
        onClick={() => onTick(!task.done)}
        className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border-2 p-0.5 transition ${
          task.done ? "border-emerald-500 bg-emerald-500 text-white" : "border-zinc-300 text-transparent hover:border-emerald-400 dark:border-zinc-600"
        }`}
      >
        {icons.check}
      </button>
      {editing ? (
        <form
          className="flex-1"
          onSubmit={(e) => {
            e.preventDefault();
            setEditing(false);
            if (text.trim() && text.trim() !== task.text) onText(text.trim());
          }}
        >
          <input className={`${inputClass} py-1`} aria-label="To-do" autoFocus maxLength={200} value={text} onChange={(e) => setText(e.target.value)} onBlur={() => setEditing(false)} />
        </form>
      ) : (
        <button type="button" className={`flex-1 truncate text-left text-sm ${task.done ? "text-zinc-400 line-through" : ""}`} title="Click to change it" onClick={() => { setText(task.text); setEditing(true); }}>
          {task.text}
        </button>
      )}
      <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-500 dark:bg-zinc-800">To-do</span>
      <button type="button" className="hidden text-xs text-zinc-500 hover:underline group-hover:inline group-focus-within:inline" onClick={onSection}>
        Section…
      </button>
      <button type="button" aria-label={`Delete the to-do ${task.text}`} disabled={busy} onClick={onRemove} className="h-6 w-6 rounded-md p-1 text-zinc-400 hover:bg-zinc-100 hover:text-red-600 dark:hover:bg-zinc-800">
        {icons.close}
      </button>
    </li>
  );
}

function AddTask({ section, onAdd }: { section: string | null; onAdd: (text: string) => void }) {
  const [text, setText] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        onAdd(text.trim());
        setText("");
      }}
    >
      <input
        className={`${inputClass} border-dashed py-1.5`}
        placeholder={section ? `Add a to-do to ${section}, then press Enter` : "Add a to-do of your own (like “Book the hotel”), then press Enter"}
        aria-label={section ? `New to-do in ${section}` : "New to-do"}
        maxLength={200}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </form>
  );
}

/** Every step of every save, as one checklist to work down. */
function AllSteps({ plan, onItem }: { plan: PlanDetails; onItem: (item: LibraryItem) => void }) {
  const [busy, setBusy] = useState(false);
  const withSteps = plan.items.filter((e) => e.item.steps.length > 0);
  async function tick(item: LibraryItem, index: number, value: boolean) {
    setBusy(true);
    try {
      onItem(await libraryApi.tick(item.id, index, value));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-5" aria-label="All steps">
      {withSteps.map((entry) => (
        <section key={entry.item.id} className="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
          <a href={`#/item/${entry.item.id}`} className="text-sm font-medium hover:text-indigo-600 dark:hover:text-indigo-400">
            {displayTitle(entry.item)}
          </a>
          {entry.note && <p className="text-xs text-zinc-500">{entry.note}</p>}
          <div className="mt-2">
            <StepsChecklist steps={entry.item.steps} checked={entry.item.steps_checked} busy={busy} onToggle={(index, value) => void tick(entry.item, index, value)} />
          </div>
        </section>
      ))}
      {withSteps.length === 0 && <p className="text-sm text-zinc-500">None of these saves has steps yet.</p>}
    </div>
  );
}

function EntryRow({
  entry,
  busy,
  first,
  last,
  ask,
  onTick,
  onUp,
  onDown,
  onSection,
  onNote,
  onRemove,
  onItem,
}: {
  entry: PlanEntry;
  busy: boolean;
  first: boolean;
  last: boolean;
  ask: Ask;
  onTick: (done: boolean) => void;
  onUp: () => void;
  onDown: () => void;
  onSection: () => void;
  onNote: (text: string) => void;
  onRemove: () => void;
  onItem: (item: LibraryItem) => void;
}) {
  const [open, setOpen] = useState(false);
  const [ticking, setTicking] = useState(false);
  const [openMenu, menu] = useContextMenu();
  const item = entry.item;
  async function editNote() {
    const text = await ask.text({ title: "Note for this save", label: "Only shown in this plan", value: entry.note ?? "", maxLength: 300 });
    if (text !== null && text !== (entry.note ?? "")) onNote(text);
  }
  const planItems: MenuItem[] = [
    { label: entry.done ? "Not done in this plan" : "Tick off in this plan", icon: icons.check, onSelect: () => onTick(!entry.done) },
    { label: entry.note ? "Change the note…" : "Add a note…", icon: icons.pencil, onSelect: () => void editNote() },
    { label: "Move to a section…", icon: icons.list, onSelect: onSection },
    { label: "Move up", icon: icons.up, disabled: first, onSelect: onUp },
    { label: "Move down", icon: icons.down, disabled: last, onSelect: onDown },
    { label: "Take out of this plan", icon: icons.close, onSelect: onRemove },
  ];
  const { done, total } = stepProgress(item);

  async function tickStep(index: number, value: boolean) {
    setTicking(true);
    try {
      onItem(await libraryApi.tick(item.id, index, value));
    } finally {
      setTicking(false);
    }
  }

  const iconButton =
    "flex h-7 w-7 items-center justify-center rounded-md p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 disabled:opacity-30 dark:hover:bg-zinc-800 dark:hover:text-zinc-200";
  return (
    <li
      className={`rounded-2xl border bg-white p-3 shadow-sm dark:bg-zinc-900 ${entry.done ? "border-emerald-200 dark:border-emerald-900" : "border-zinc-200 dark:border-zinc-800"}`}
      onContextMenu={(event) => openMenu(event, saveMenuItems(item, { onChange: onItem, ask, extra: planItems }), displayTitle(item))}
    >
      {menu}
      <div className="flex items-center gap-3">
        <button
          type="button"
          role="checkbox"
          aria-checked={entry.done}
          aria-label={`${displayTitle(item)} done`}
          disabled={busy}
          onClick={() => onTick(!entry.done)}
          className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 p-0.5 transition ${
            entry.done ? "border-emerald-500 bg-emerald-500 text-white" : "border-zinc-300 text-transparent hover:border-emerald-400 dark:border-zinc-600"
          }`}
        >
          {icons.check}
        </button>
        <Thumb item={item} showDuration={false} className="h-16 w-12 shrink-0 rounded-lg" />
        <div className="min-w-0 flex-1">
          <a href={`#/item/${item.id}`} className={`block truncate font-medium hover:text-indigo-600 dark:hover:text-indigo-400 ${entry.done ? "text-zinc-400 line-through" : ""}`}>
            {displayTitle(item)}
          </a>
          <p className="truncate text-xs text-zinc-500">
            {[item.kind_label ?? item.platform_name, total > 0 ? `${done}/${total} steps` : null].filter(Boolean).join(" · ")}
          </p>
          <button type="button" className={`mt-0.5 block max-w-full truncate text-left text-xs ${entry.note ? "text-zinc-700 dark:text-zinc-300" : "text-zinc-400 hover:text-zinc-600"}`} onClick={() => void editNote()}>
            {entry.note ? `Note: ${entry.note}` : "Add a note"}
          </button>
        </div>
        {total > 0 && (
          <Button size="sm" variant="ghost" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Hide steps" : "Steps"}
          </Button>
        )}
        <button type="button" className={iconButton} disabled={first || busy} onClick={onUp} aria-label="Move up">
          {icons.up}
        </button>
        <button type="button" className={iconButton} disabled={last || busy} onClick={onDown} aria-label="Move down">
          {icons.down}
        </button>
        <button type="button" className={iconButton} disabled={busy} onClick={onRemove} aria-label="Take out of this plan" title="Take out of this plan">
          {icons.close}
        </button>
      </div>
      {open && total > 0 && (
        <div className="mt-3 border-t border-zinc-100 pt-3 dark:border-zinc-800">
          <StepsChecklist steps={item.steps} checked={item.steps_checked} busy={ticking} onToggle={(index, value) => void tickStep(index, value)} />
        </div>
      )}
    </li>
  );
}

function AddSaves({ planIds, onAdd }: { planIds: number[]; onAdd: (ids: number[]) => void }) {
  const [words, setWords] = useState("");
  const [results, setResults] = useState<LibraryItem[] | null>(null);
  const [picked, setPicked] = useState<number[]>([]);

  useEffect(() => {
    let stale = false;
    const timer = window.setTimeout(() => {
      libraryApi
        .items({ ...DEFAULT_QUERY, q: words.trim() })
        .then((page) => !stale && setResults(page.items))
        .catch(() => !stale && setResults([]));
    }, 250);
    return () => {
      stale = true;
      window.clearTimeout(timer);
    };
  }, [words]);

  const toggle = (id: number) => setPicked((old) => (old.includes(id) ? old.filter((p) => p !== id) : [...old, id]));
  const list = (results ?? []).filter((item) => !planIds.includes(item.id));
  return (
    <div className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-4 dark:border-indigo-900 dark:bg-indigo-950/20">
      <div className="flex gap-2">
        <input
          type="search"
          autoFocus
          className={inputClass}
          placeholder="Find saves to add: a word from the title, caption, notes or tags"
          aria-label="Find saves to add"
          value={words}
          onChange={(e) => setWords(e.target.value)}
        />
        <Button
          disabled={picked.length === 0}
          onClick={() => {
            onAdd(picked);
            setPicked([]);
          }}
        >
          Add {picked.length || ""}
        </Button>
      </div>
      <ul className="mt-3 max-h-80 space-y-1 overflow-y-auto" aria-label="Saves you can add">
        {results === null && <li className="text-sm text-zinc-500">Loading…</li>}
        {results !== null && list.length === 0 && <li className="text-sm text-zinc-500">Nothing found.</li>}
        {list.map((item) => (
          <li key={item.id}>
            <label className="flex cursor-pointer items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-white dark:hover:bg-zinc-900">
              <input type="checkbox" checked={picked.includes(item.id)} onChange={() => toggle(item.id)} />
              <Thumb item={item} showDuration={false} className="h-10 w-8 shrink-0 rounded" />
              <span className="min-w-0 flex-1 truncate text-sm">{displayTitle(item)}</span>
              <span className="text-xs text-zinc-500">{item.kind_label ?? item.platform_name}</span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}
