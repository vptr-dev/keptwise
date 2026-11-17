// An item's next steps as a checklist. Ticking the first one puts the item
// on the Plans screen. Keys 1-9 tick steps on the item page.
import ProgressBar from "../../components/ProgressBar";
import { icons } from "../../components/icons";

export default function StepsChecklist({
  steps,
  checked,
  busy,
  onToggle,
}: {
  steps: string[];
  checked: boolean[];
  busy: boolean;
  onToggle: (index: number, done: boolean) => void;
}) {
  const done = checked.filter(Boolean).length;
  return (
    <div>
      <div className="mb-3 flex items-center gap-3">
        <ProgressBar done={done} total={steps.length} label="Steps done" />
        <span className="shrink-0 text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
          {done} of {steps.length} done
        </span>
      </div>
      <ol className="space-y-1.5">
        {steps.map((step, index) => {
          const isDone = checked[index] ?? false;
          return (
            <li key={index}>
              <label
                className={`flex cursor-pointer items-start gap-3 rounded-xl border px-3 py-2.5 text-sm transition ${
                  isDone
                    ? "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/60 dark:bg-emerald-950/30"
                    : "border-zinc-200 bg-white hover:border-indigo-300 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-indigo-700"
                }`}
              >
                <input
                  type="checkbox"
                  className="peer sr-only"
                  aria-label={step}
                  checked={isDone}
                  disabled={busy}
                  onChange={(event) => onToggle(index, event.target.checked)}
                />
                <span
                  aria-hidden="true"
                  className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border p-0.5 transition peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-indigo-500 ${
                    isDone
                      ? "border-emerald-500 bg-emerald-500 text-white"
                      : "border-zinc-300 text-transparent dark:border-zinc-600"
                  }`}
                >
                  {icons.check}
                </span>
                <span className={`flex-1 leading-relaxed ${isDone ? "text-zinc-500 line-through dark:text-zinc-400" : ""}`}>
                  {step}
                </span>
                {index < 9 && (
                  <kbd aria-hidden="true" className="hidden shrink-0 rounded border border-zinc-200 px-1.5 text-[10px] text-zinc-400 sm:inline dark:border-zinc-700">
                    {index + 1}
                  </kbd>
                )}
              </label>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
