// Step 2 on the Sort page: the AI writes notes for the saves that have a
// transcript (title, summary, key details, steps), and picks the collection
// and tags that fit. By default those picks are suggestions you approve in
// Unsorted; two switches let it file and tag by itself instead. Start a
// batch here, or let notes start by themselves whenever transcripts finish.
import { useCallback, useEffect, useState, type ReactNode } from "react";

import JobCard from "../../components/JobCard";
import { icons } from "../../components/icons";
import { Button, Card, Notice } from "../../components/ui";
import { errorCode, errorText } from "../../lib/api";
import { isActive, onJobUpdate, useJobs, type Job } from "../../lib/jobs";
import { navigate } from "../../lib/router";
import { useAiSwitch } from "./SortingSettings";
import { sortingApi, type NotesOverview } from "./sortingApi";

const BATCH_SIZES = [20, 50, 200];
const SETTINGS_CODES = ["model_missing", "missing_key", "missing_model", "unreachable"];

export default function NotesStep({ transcribing = false }: { transcribing?: boolean }) {
  const jobs = useJobs();
  const [notes, setNotes] = useState<NotesOverview | null>(null);
  const [started, setStarted] = useState<Job | null>(null);
  const [problem, setProblem] = useState<{ text: string; code: string | null } | null>(null);
  const [pending, setPending] = useState<{ text: string; go: () => void } | null>(null);
  const [auto, setAuto] = useAiSwitch("auto_notes", false);
  const [autoSort, setAutoSort] = useAiSwitch("auto_sort", false);
  const [autoTag, setAutoTag] = useAiSwitch("auto_tag", false);

  const refresh = useCallback(() => {
    sortingApi.overview().then(setNotes).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);
  // Transcripts finishing, and notes being written, both change the count.
  useEffect(() => {
    let last = "";
    return onJobUpdate((job) => {
      if (job.kind !== "notes" && job.kind !== "enrich") return;
      const now = `${job.id}:${job.progress}:${job.status}`;
      if (now !== last) {
        last = now;
        refresh();
      }
    });
  }, [refresh]);

  const noteJobs = jobs.filter((job) => job.kind === "notes");
  const running = noteJobs.find(isActive);
  const currentId = running?.id ?? Math.max(started?.id ?? 0, noteJobs[0]?.id ?? 0);
  const current = noteJobs.find((job) => job.id === currentId) ?? started ?? undefined;
  const busy = running !== undefined;

  async function start(count: number | null, confirm = false) {
    setProblem(null);
    setPending(null);
    try {
      setStarted(await sortingApi.startNotes(count, confirm));
    } catch (e) {
      if (errorCode(e) === "confirm_cost") setPending({ text: errorText(e), go: () => void start(count, true) });
      else setProblem({ text: errorText(e), code: errorCode(e) });
    }
  }

  const waiting = notes?.counts.waiting ?? 0;
  const cloud = notes?.is_cloud ?? false;
  const limit = notes?.cloud_batch_limit ?? 50;
  const sizes = BATCH_SIZES.filter((size) => size < waiting && !(cloud && size > limit));
  const allAllowed = waiting > 0 && !(cloud && waiting > limit);

  return (
    <>
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <span className="h-5 w-5 text-indigo-500">{icons.sparkle}</span>
          <h2 className="font-medium">Write the notes</h2>
          <span className="ml-auto text-xs text-zinc-500">Using {notes?.ai_label ?? "…"}</span>
        </div>
        <p className="kw-tip mt-1 text-sm text-zinc-500 dark:text-zinc-400" data-testid="notes-waiting">
          {waiting > 0
            ? `${waiting.toLocaleString()} save${waiting === 1 ? " has" : "s have"} a transcript and ${waiting === 1 ? "is" : "are"} waiting for notes.`
            : "Every save with a transcript has its notes."}{" "}
          The AI writes a title, a summary, the key details and the steps, and picks the collection and tags that fit.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {sizes.map((size) => (
            <Button key={size} variant={size === sizes[0] ? "primary" : "secondary"} disabled={busy} onClick={() => void start(size)}>
              Write next {size}
            </Button>
          ))}
          {allAllowed && (
            <Button variant={sizes.length ? "secondary" : "primary"} disabled={busy} onClick={() => void start(null)}>
              Write all {waiting.toLocaleString()}
            </Button>
          )}
          {waiting === 0 && (
            <Button variant="secondary" disabled>
              Nothing waiting
            </Button>
          )}
        </div>
        {cloud && waiting > limit && (
          <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">A cloud AI does at most {limit} at a time, so each batch stays cheap.</p>
        )}
        <div className="mt-4 space-y-3 border-t border-zinc-100 pt-4 dark:border-zinc-800">
          <Switch
            label="Put into collections automatically (best fit)"
            on={autoSort}
            onChange={setAutoSort}
            hint={
              autoSort
                ? "The AI puts each save in the collection that fits best. Ones it isn't sure about wait in Unsorted."
                : "Off: every save waits in Unsorted with the AI's suggestion, for you to accept or change."
            }
          />
          <Switch
            label="Add tags automatically"
            on={autoTag}
            onChange={setAutoTag}
            hint={autoTag ? "The AI's tags go straight on." : "Off: the AI's tags are suggestions you add with one click."}
          />
          <Switch
            label="Write notes by themselves when transcripts finish"
            on={cloud ? false : auto}
            disabled={cloud}
            onChange={setAuto}
            hint={
              cloud
                ? "Only with an AI on this PC: a cloud AI costs money, so it always waits for you to start it."
                : `Then one press on “Get transcripts” does everything.${transcribing && auto ? " Notes will start when this transcripts job ends." : ""}`
            }
          />
        </div>
      </Card>

      {pending && (
        <Notice tone="warning" onClose={() => setPending(null)}>
          <p>{pending.text}</p>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={pending.go}>
              Yes, go ahead
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setPending(null)}>
              Cancel
            </Button>
          </div>
        </Notice>
      )}
      {problem && (
        <Notice tone="error" onClose={() => setProblem(null)}>
          <p>{problem.text}</p>
          {problem.code && SETTINGS_CODES.includes(problem.code) && (
            <div className="mt-3">
              <Button size="sm" variant="secondary" onClick={() => navigate("/settings?section=ai")}>
                Open AI settings
              </Button>
            </div>
          )}
        </Notice>
      )}
      {current && <JobCard job={current} name="AI notes job" />}
    </>
  );
}

function Switch({
  label,
  hint,
  on,
  onChange,
  disabled = false,
}: {
  label: string;
  hint: ReactNode;
  on: boolean | null;
  onChange: (on: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className="flex items-start gap-3">
      <input
        type="checkbox"
        role="switch"
        className="mt-0.5 h-4 w-4 accent-indigo-600"
        checked={on ?? false}
        disabled={on === null || disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>
        <span className="block text-sm font-medium">{label}</span>
        <span className="kw-tip block text-xs text-zinc-500 dark:text-zinc-400">{hint}</span>
      </span>
    </label>
  );
}
