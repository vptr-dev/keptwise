// What the right-click menu on a save offers, wherever the save is shown
// (Library, a collection, Needs review, a plan). Changes say so in a small
// message with Undo where it can be undone.
import type { Ask } from "../../components/Dialog";
import type { MenuItem } from "../../components/ContextMenu";
import { toast } from "../../components/Toasts";
import { icons } from "../../components/icons";
import { errorCode, errorText } from "../../lib/api";
import { navigate } from "../../lib/router";
import { announceChange, organizeApi } from "../organize/organizeApi";
import { sortingApi, type ItemCard } from "../sorting/sortingApi";
import { libraryApi, type LibraryItem } from "./libraryApi";
import { CollectionPanel, PlanPanel, TagsPanel } from "./QuickActions";

export type SaveMenuOptions = {
  onChange: (item: LibraryItem) => void;
  ask: Ask;
  from?: { id: number; name: string } | null; // the collection it's shown in
  extra?: MenuItem[]; // things only this screen offers, shown first
};

/** Run a change; say what happened, or why it didn't. */
async function attempt(task: () => Promise<unknown>, done?: string, undo?: () => Promise<unknown>) {
  try {
    await task();
    announceChange();
    if (done) toast(done, undo ? { undo: async () => { await undo(); announceChange(); } } : {});
  } catch (e) {
    toast(errorText(e), { tone: "error" });
  }
}

/** Start an AI job for this one save, asking first when it costs money. */
async function aiJob(ask: Ask, start: (confirm: boolean) => Promise<unknown>, started: string) {
  try {
    await start(false);
    toast(started);
  } catch (e) {
    if (errorCode(e) !== "confirm_cost") return toast(errorText(e), { tone: "error" });
    if (await ask.confirm({ title: "Use the cloud AI?", body: errorText(e), confirm: "Yes, go ahead" })) {
      await start(true).then(() => toast(started)).catch((err) => toast(errorText(err), { tone: "error" }));
    }
  }
}

export function saveMenuItems(raw: LibraryItem | ItemCard, { onChange, ask, from, extra = [] }: SaveMenuOptions): MenuItem[] {
  const item = raw as LibraryItem;
  const merge = (card: ItemCard | LibraryItem) => {
    onChange({ ...item, ...card } as LibraryItem);
    announceChange();
  };
  const patch = (change: Partial<Pick<LibraryItem, "done" | "safe_to_unsave" | "unsaved" | "deleted">>) => libraryApi.patch(item.id, change).then(merge);
  const platform = item.platform_name;

  const items: MenuItem[] = [
    ...extra,
    ...(extra.length ? [{ kind: "divider" } as MenuItem] : []),
    { label: "Open", icon: icons.library, onSelect: () => navigate(`/item/${item.id}`) },
    {
      label: `Open on ${platform}`,
      icon: icons.external,
      onSelect: () => void attempt(() => libraryApi.openInBrowser(item.id)),
    },
    {
      label: "Copy link",
      icon: icons.link,
      onSelect: () =>
        void navigator.clipboard
          ?.writeText(item.url)
          .then(() => toast("Link copied."))
          .catch(() => toast("Couldn't copy the link.", { tone: "error" })),
    },
    { kind: "divider" },
    { kind: "panel", label: "Tags…", icon: icons.tag, title: "Tags", panel: () => <TagsPanel item={item} onChange={merge} /> },
    { kind: "panel", label: "Collections…", icon: icons.folder, title: "Collections", panel: () => <CollectionPanel item={item} onChange={merge} /> },
    { kind: "panel", label: "Add to a plan…", icon: icons.plans, title: "Plans", panel: () => <PlanPanel item={item} onChange={merge} /> },
  ];
  if (from && item.collections.some((c) => c.id === from.id)) {
    items.push({
      label: `Take out of “${from.name}”`,
      icon: icons.close,
      onSelect: () =>
        void attempt(
          () => sortingApi.removeFrom(item.id, from.id).then(merge),
          `Taken out of “${from.name}”.`,
          () => sortingApi.move(item.id, null, from.id).then(merge),
        ),
    });
  }
  items.push(
    { kind: "divider" },
    item.unsaved
      ? { label: `Still saved on ${platform}`, icon: icons.unsave, onSelect: () => void attempt(() => patch({ unsaved: false }), "Marked as still saved.") }
      : {
          label: `I've unsaved it on ${platform}`,
          icon: icons.unsave,
          onSelect: () => void attempt(() => patch({ unsaved: true }), `Marked as unsaved on ${platform}.`, () => patch({ unsaved: false })),
        },
    {
      label: item.safe_to_unsave ? "Take off the Unsave list" : "Put on the Unsave list",
      icon: icons.list,
      onSelect: () =>
        void attempt(
          () => patch({ safe_to_unsave: !item.safe_to_unsave }),
          item.safe_to_unsave ? "Taken off the Unsave list." : "Put on the Unsave list.",
          () => patch({ safe_to_unsave: !!item.safe_to_unsave }),
        ),
    },
    { kind: "divider" },
    { kind: "heading", label: "AI" },
    { label: "Ask the AI Assistant about it", icon: icons.chat, onSelect: () => navigate(`/chat?items=${item.id}`) },
    {
      label: "Sort it into collections",
      icon: icons.sparkle,
      disabled: item.status !== "processed",
      onSelect: () => void aiJob(ask, (confirm) => sortingApi.resort("all", true, confirm, [item.id]), "AI sort started for this save."),
    },
    {
      label: "Suggest tags",
      icon: icons.sparkle,
      disabled: item.status !== "processed",
      onSelect: () => void aiJob(ask, (confirm) => sortingApi.aiTags("with_notes", confirm, [item.id]), "AI tags started for this save."),
    },
    { kind: "divider" },
    {
      label: "Delete",
      icon: icons.trash,
      danger: true,
      hint: "to the Archive",
      onSelect: () => void attempt(() => patch({ deleted: true }), "Deleted. It's in the Archive.", () => patch({ deleted: false })),
    },
  );
  return items;
}

/** The menu when several picked saves are right-clicked together. */
export function selectionMenuItems(ids: number[], { onDone, onClear }: { onDone: () => void; onClear: () => void }): MenuItem[] {
  const many = `${ids.length} saves`;
  const bulk = (action: "delete" | "restore" | "unsaved" | "safe", done: string, undo?: "restore") =>
    attempt(
      () => organizeApi.bulk({ item_ids: ids, action }).then(onDone),
      done,
      undo ? () => organizeApi.bulk({ item_ids: ids, action: undo }).then(onDone) : undefined,
    );
  return [
    {
      label: `Ask the AI Assistant about these ${ids.length}`,
      icon: icons.chat,
      disabled: ids.length > 30,
      hint: ids.length > 30 ? "30 at most" : undefined,
      onSelect: () => navigate(`/chat?items=${ids.join(",")}`),
    },
    { label: "Make a plan with them", icon: icons.plans, onSelect: () => navigate(`/chat?tool=plan&items=${ids.slice(0, 30).join(",")}`) },
    { kind: "divider" },
    { label: "Put on the Unsave list", icon: icons.list, onSelect: () => void bulk("safe", `Put ${many} on the Unsave list.`) },
    { label: "I've unsaved them", icon: icons.unsave, onSelect: () => void bulk("unsaved", `Marked ${many} as unsaved.`) },
    { kind: "divider" },
    { label: `Delete ${many}`, icon: icons.trash, danger: true, hint: "to the Archive", onSelect: () => void bulk("delete", `Deleted ${many}. They're in the Archive.`, "restore") },
    { kind: "divider" },
    { label: "Clear the selection", icon: icons.close, hint: "Esc", onSelect: onClear },
  ];
}
