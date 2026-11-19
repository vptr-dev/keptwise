import { useRef, useState } from "react";

import { Notice } from "../../components/ui";
import { useSortingSettings } from "./SortingSettings";

const CHOICES = [
  { key: "auto_sort", label: "Put into collections automatically", help: "File confident AI matches in your collections. Other matches stay suggestions." },
  { key: "auto_tag", label: "Add tags automatically", help: "Apply the AI’s tags as it writes notes. Leave this off to approve them yourself." },
  { key: "auto_notes", label: "Write notes by themselves when transcripts finish", help: "Write waiting notes after a successful transcript batch when you use a local AI." },
] as const;

export default function WorkflowControls({
  cloud,
  transcribing = false,
  onSaving,
}: {
  cloud: boolean;
  transcribing?: boolean;
  onSaving?: (busy: boolean) => void;
}) {
  const { data, error, saved, save } = useSortingSettings();
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);

  async function change(key: (typeof CHOICES)[number]["key"], enabled: boolean) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    onSaving?.(true);
    try {
      await save({ [key]: enabled });
    } finally {
      pending.current = false;
      setBusy(false);
      onSaving?.(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && <Notice tone="error">{error}</Notice>}
      {!data && !error && <p role="status" className="text-sm text-zinc-500">Loading workflow settings…</p>}
      {data && CHOICES.map(({ key, label, help }) => {
        const localOnly = key === "auto_notes" && cloud;
        const checked = !localOnly && !!data.settings[key];
        const description = localOnly
          ? "With cloud AI, each paid batch starts after you confirm it. Your local preference is kept."
          : key === "auto_notes" && checked && transcribing
            ? "Notes will start when the current transcript batch finishes."
            : help;
        return (
          <label key={key} className="flex items-start gap-3">
            <input
              type="checkbox"
              role="switch"
              aria-label={label}
              className="mt-0.5 h-4 w-4 shrink-0 accent-indigo-600"
              checked={checked}
              disabled={busy || localOnly}
              onChange={(event) => void change(key, event.target.checked)}
            />
            <span>
              <span className="block text-sm font-medium">{label}</span>
              <span className="block text-xs text-zinc-500 dark:text-zinc-400">{description}</span>
            </span>
          </label>
        );
      })}
      {(busy || (saved && !error)) && <p role="status" className="text-xs text-zinc-500">{busy ? "Saving…" : "Changes saved."}</p>}
    </div>
  );
}
