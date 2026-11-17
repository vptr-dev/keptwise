// Links from the platforms' own collections to yours: "From TikTok
// collection 'recipes', add to my Food". Pick a collection for each, and
// whether its saves are filed by themselves (Auto: now, and after every
// import) or only when you press "Add now" (Manual). Links never make new
// collections on their own, and never take a save out of where you put it.
import { useCallback, useEffect, useState } from "react";

import { icons } from "../../components/icons";
import { Badge, Button, Notice, Segmented } from "../../components/ui";
import { errorText } from "../../lib/api";
import { PLATFORM_DOTS } from "../../lib/scope";
import { Tip } from "../../lib/tips";
import type { Collection } from "../sorting/sortingApi";
import { announceChange, organizeApi, type PlatformLink, type PlatformLinks as Links } from "./organizeApi";

const MAKE_NEW = "new";

export default function PlatformLinks({ collections, spaceId }: { collections: Collection[]; spaceId?: number }) {
  const [data, setData] = useState<Links | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "linked" | "not_linked">("all");

  const load = useCallback(() => {
    organizeApi.platformLinks(spaceId).then(setData).catch((e) => setProblem(errorText(e)));
  }, [spaceId]);
  useEffect(load, [load]);

  async function run(task: () => Promise<Links>, done?: (result: Links) => string | null) {
    setProblem(null);
    setMessage(null);
    try {
      const result = await task();
      setData(result);
      setMessage(done?.(result) ?? null);
      announceChange();
    } catch (e) {
      setProblem(errorText(e));
    }
  }

  function link(entry: PlatformLink, choice: string, mode = entry.mode) {
    const filedText = (r: Links) => (r.filed ? `Filed ${r.filed.toLocaleString()} save${r.filed === 1 ? "" : "s"}.` : null);
    if (choice === MAKE_NEW) {
      return run(
        () => organizeApi.linkPlatform({ platform: entry.platform, name: entry.name, collection_id: null, mode, create_collection: true, space_id: spaceId }),
        filedText,
      );
    }
    return run(
      () => organizeApi.linkPlatform({ platform: entry.platform, name: entry.name, collection_id: choice ? Number(choice) : null, mode }),
      filedText,
    );
  }

  const links = data?.links ?? [];
  const shown = links.filter((l) => filter === "all" || (filter === "linked") === (l.collection_id !== null));
  const platforms = [...new Set(shown.map((l) => l.platform))];
  const namesOnly = links.some((l) => !l.membership_known);
  const linkedCount = links.filter((l) => l.collection_id !== null).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-medium">Or choose one by one</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Link each collection you made on TikTok, YouTube, Instagram or Facebook to one of yours.{" "}
            {links.length > 0 && `${linkedCount} of ${links.length} linked.`}
          </p>
        </div>
        {links.length > 0 && (
          <Segmented
            label="Show"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All" },
              { value: "not_linked", label: "Not linked" },
              { value: "linked", label: "Linked" },
            ]}
          />
        )}
      </div>

      <Tip id="platform-links-how">
        <b>Auto</b> files every save from that collection into yours now, and again after each import.{" "}
        <b>Manual</b> waits until you press <b>Add now</b>. Either way, nothing is taken out of where you put it, and
        no new collections are made unless you choose “Make it a new collection”.
      </Tip>
      {namesOnly && (
        <Tip id="platform-links-tiktok" tone="warning">
          TikTok's data export only lists the <b>names</b> of your collections, not which videos are in each one. So
          a TikTok name can be linked (the AI then uses it as a hint when sorting), but there are no saves to copy
          over. To fill your collections from TikTok saves, use <b>AI sort</b> instead.
        </Tip>
      )}
      {problem && <Notice tone="error" onClose={() => setProblem(null)}>{problem}</Notice>}
      {message && <Notice tone="success" onClose={() => setMessage(null)}>{message}</Notice>}

      {data && links.length === 0 && (
        <p className="rounded-2xl border border-dashed border-zinc-300 p-8 text-center text-sm text-zinc-500 dark:border-zinc-700">
          No platform collections found yet. They come with your data export: import it on the Import screen.
        </p>
      )}
      {platforms.map((platform) => (
        <section key={platform} className="overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <h3 className="flex items-center gap-2 border-b border-zinc-100 px-4 py-2.5 text-sm font-semibold dark:border-zinc-800">
            <span className={`h-3 w-3 rounded-full ${PLATFORM_DOTS[platform] ?? "bg-zinc-400"}`} aria-hidden="true" />
            {shown.find((l) => l.platform === platform)?.platform_name}
          </h3>
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {shown
              .filter((l) => l.platform === platform)
              .map((entry) => (
                <LinkRow
                  key={`${entry.platform}:${entry.name}`}
                  entry={entry}
                  collections={collections}
                  roomLeft={data?.room_left ?? 0}
                  onLink={(choice, mode) => link(entry, choice, mode)}
                  onApply={() =>
                    run(() => organizeApi.applyPlatform(entry.platform, entry.name), (r) =>
                      `Added ${(r.filed ?? 0).toLocaleString()} save${r.filed === 1 ? "" : "s"} to ${entry.collection_name}.`,
                    )
                  }
                />
              ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function LinkRow({
  entry,
  collections,
  roomLeft,
  onLink,
  onApply,
}: {
  entry: PlatformLink;
  collections: Collection[];
  roomLeft: number;
  onLink: (choice: string, mode: "auto" | "manual") => void;
  onApply: () => void;
}) {
  const linked = entry.collection_id !== null;
  const exists = collections.some((c) => c.name.toLowerCase() === entry.name.toLowerCase());
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3" data-testid={`link-${entry.name}`}>
      <div className="min-w-40 flex-1">
        <p className="font-medium">“{entry.name}”</p>
        <p className="text-xs text-zinc-500">
          {entry.membership_known
            ? `${entry.count.toLocaleString()} save${entry.count === 1 ? "" : "s"}${linked ? ` · ${entry.filed.toLocaleString()} filed` : ""}`
            : "Name only (the export doesn't say which saves)"}
        </p>
      </div>
      <span className="h-4 w-4 text-zinc-400" aria-hidden="true">
        {icons.link}
      </span>
      <select
        aria-label={`App collection for “${entry.name}”`}
        value={entry.collection_id !== null ? String(entry.collection_id) : ""}
        onChange={(e) => onLink(e.target.value, entry.mode)}
        className={`max-w-56 rounded-lg border px-2.5 py-1.5 text-sm dark:bg-zinc-900 ${
          linked ? "border-indigo-300 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-950/40" : "border-zinc-300 bg-white dark:border-zinc-700"
        }`}
      >
        <option value="">Not linked</option>
        {collections.map((c) => (
          <option key={c.id} value={c.id}>
            {"  ".repeat(c.depth)}Add to {c.name}
          </option>
        ))}
        {!exists && roomLeft > 0 && <option value={MAKE_NEW}>Make it a new collection, “{entry.name}”</option>}
      </select>
      {linked && entry.membership_known && <Segmented
        label={`How “${entry.name}” is filed`}
        value={entry.mode}
        onChange={(mode) => onLink(entry.collection_id !== null ? String(entry.collection_id) : "", mode)}
        options={[
          { value: "auto", label: "Auto" },
          { value: "manual", label: "Manual" },
        ]}
      />}
      {linked && entry.mode === "manual" && entry.membership_known && (
        <Button size="sm" variant="secondary" onClick={onApply} disabled={entry.filed >= entry.count}>
          {entry.filed >= entry.count ? "All added" : "Add now"}
        </Button>
      )}
      {linked && entry.mode === "auto" && entry.membership_known && <Badge tone="green">Filed by itself</Badge>}
      {linked && !entry.membership_known && (
        <span title="When the AI sorts, it's told this name belongs in your collection">
          <Badge tone="indigo">Used as an AI hint</Badge>
        </span>
      )}
    </li>
  );
}
