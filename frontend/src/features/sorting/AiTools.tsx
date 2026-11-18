// The rest of the Sort page: ask the AI again (new suggestions after you
// made collections, tags for saves that have none), and take back what the
// AI did. Everything here can also be undone with Undo (top right).
import { useCallback, useEffect, useState } from "react";

import { useDialog } from "../../components/Dialog";
import JobCard from "../../components/JobCard";
import { icons } from "../../components/icons";
import { Button, Card, Notice } from "../../components/ui";
import { toast } from "../../components/Toasts";
import { errorCode, errorText } from "../../lib/api";
import { isActive, onJobUpdate, useJobs, type Job } from "../../lib/jobs";
import { announceChange, onOrganizeChange } from "../organize/organizeApi";
import { CollectionSortOptions, TagOptions } from "./SortingSettings";
import { sortingApi, type Collection, type LibraryCounts } from "./sortingApi";

const KINDS = ["sort", "tags"];

function useCounts(): [LibraryCounts | null, () => void] {
  const [counts, setCounts] = useState<LibraryCounts | null>(null);
  const refresh = useCallback(() => {
    sortingApi.overview().then((o) => setCounts(o.counts)).catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => onOrganizeChange(refresh), [refresh]);
  useEffect(() => onJobUpdate((job) => !isActive(job) && refresh()), [refresh]);
  return [counts, refresh];
}

/** "Suggest again" for Unsorted, and tags for saves without any. */
export function AskAgain() {
  const jobs = useJobs();
  const [counts] = useCounts();
  const [started, setStarted] = useState<Job | null>(null);
  const [pending, setPending] = useState<{ text: string; go: () => void } | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  const mine = jobs.filter((job) => KINDS.includes(job.kind));
  const running = mine.find(isActive);
  const current = mine.find((job) => job.id === (running?.id ?? started?.id)) ?? (started && mine.length === 0 ? started : undefined);

  async function run(task: (confirm: boolean) => Promise<Job>, confirm = false) {
    setProblem(null);
    setPending(null);
    try {
      setStarted(await task(confirm));
    } catch (e) {
      if (errorCode(e) === "confirm_cost") setPending({ text: errorText(e), go: () => void run(task, true) });
      else setProblem(errorText(e));
    }
  }

  const unsorted = counts?.unsorted ?? 0;
  const untagged = counts?.untagged ?? 0;
  if (!unsorted && !untagged && !current) return null;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {unsorted > 0 && (
          <Button variant="secondary" size="sm" disabled={!!running} onClick={() => void run((c) => sortingApi.resort("unsorted", true, c))}>
            <span className="h-4 w-4">{icons.sparkle}</span>
            Suggest again for the {unsorted.toLocaleString()} in Unsorted
          </Button>
        )}
        {untagged > 0 && (
          <Button variant="secondary" size="sm" disabled={!!running} onClick={() => void run((c) => sortingApi.aiTags("untagged", c))}>
            <span className="h-4 w-4">{icons.tag}</span>
            Suggest tags for {untagged.toLocaleString()} save{untagged === 1 ? "" : "s"} with none
          </Button>
        )}
      </div>
      <p className="kw-tip text-xs text-zinc-500 dark:text-zinc-400">
        Handy after you've made new collections. Saves you placed yourself are never moved.
      </p>
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
          {problem}
        </Notice>
      )}
      {current && <JobCard job={current} name={current.kind === "sort" ? "AI suggestions" : "AI tags"} />}
    </div>
  );
}

/** Take back what the AI did: its suggestions, its tags, its placements. */
export function ClearAi() {
  const [counts, refresh] = useCounts();
  const [ask, dialog] = useDialog();
  const [problem, setProblem] = useState<string | null>(null);

  async function clear(what: "suggestions" | "ai_tags" | "ai_collections", title: string, body: string) {
    if (!(await ask.confirm({ title, body, confirm: "Clear", danger: true }))) return;
    setProblem(null);
    try {
      const done = await sortingApi.clear(what);
      toast(`Cleared ${done.cleared.toLocaleString()}. Undo (top right) brings them back.`);
    } catch (e) {
      setProblem(errorText(e));
    }
    announceChange();
    refresh();
  }

  const suggested = (counts?.suggested ?? 0) + (counts?.tag_suggested ?? 0);
  const aiTagged = counts?.ai_tagged ?? 0;
  const aiFiled = counts?.ai_filed ?? 0;
  return (
    <Card>
      {dialog}
      <h2 className="font-medium">Clear what the AI did</h2>
      <p className="kw-tip mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        Only the AI's work goes: your own tags and the saves you placed yourself always stay.
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          variant="secondary"
          size="sm"
          disabled={!suggested}
          onClick={() =>
            void clear("suggestions", "Forget the AI's suggestions?", "Every collection and tag the AI suggested is forgotten. Nothing is moved.")
          }
        >
          Forget its suggestions ({suggested.toLocaleString()})
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!aiTagged}
          onClick={() => void clear("ai_tags", "Remove the AI's tags?", `${aiTagged.toLocaleString()} tags the AI put on come off.`)}
        >
          Remove its tags ({aiTagged.toLocaleString()})
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!aiFiled}
          onClick={() =>
            void clear(
              "ai_collections",
              "Take saves out of the AI's collections?",
              `${aiFiled.toLocaleString()} placements the AI made are undone; those saves go back to Unsorted.`,
            )
          }
        >
          Undo its placements ({aiFiled.toLocaleString()})
        </Button>
      </div>
      {problem && (
        <div className="mt-3">
          <Notice tone="error" onClose={() => setProblem(null)}>
            {problem}
          </Notice>
        </div>
      )}
    </Card>
  );
}

/** How the AI picks collections and tags: rules, how many, how sure. */
export function AiOptions() {
  const [collections, setCollections] = useState<Collection[]>([]);
  useEffect(() => {
    sortingApi.collections().then((o) => setCollections(o.collections)).catch(() => undefined);
  }, []);
  return (
    <details className="rounded-2xl border border-zinc-200 bg-white px-5 py-4 dark:border-zinc-800 dark:bg-zinc-900">
      <summary className="cursor-pointer font-medium">Options: how the AI picks collections and tags, and your rules</summary>
      <div className="mt-5 space-y-8">
        <CollectionSortOptions collections={collections} />
        <div className="space-y-5 border-t border-zinc-100 pt-5 dark:border-zinc-800">
          <h3 className="text-sm font-semibold">Tags</h3>
          <TagOptions />
        </div>
      </div>
    </details>
  );
}
