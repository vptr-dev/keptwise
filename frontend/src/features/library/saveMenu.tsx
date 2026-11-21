// What the right-click menu on a save offers, wherever the save is shown
// (Library, a collection, Unsorted, a plan). Changes say so in a small
// message with Undo where it can be undone. Unsaving is only on the Unsave
// page, and the AI's sorting only on the Sort page.
import type { Ask } from "../../components/Dialog";
import type { MenuItem } from "../../components/ContextMenu";
import { toast } from "../../components/Toasts";
import { icons } from "../../components/icons";
import { errorText } from "../../lib/api";
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

export function saveMenuItems(raw: LibraryItem | ItemCard, { onChange, from, extra = [] }: SaveMenuOptions): MenuItem[] {
  const item = raw as LibraryItem;
  const merge = (card: ItemCard | LibraryItem) => {
    onChange({ ...item, ...card } as LibraryItem);
    announceChange();
  };
  const patch = (change: Partial<Pick<LibraryItem, "deleted">>) => libraryApi.patch(item.id, change).then(merge);
  const platform = item.platform_name;

  const items: MenuItem[] = [
    ...extra,
    ...(extra.length ? [{ kind: "divider" } as MenuItem] : []),
    { label: "Open", icon: icons.open, onSelect: () => navigate(`/item/${item.id}`) },
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
  if (!item.deleted && !item.gone && (item.error || item.status === "failed")) {
    items.push({
      label: "Mark unavailable",
      onSelect: () => void attempt(
        () => libraryApi.patch(item.id, { unavailable: true }).then(merge),
        "Moved to Unavailable.",
        () => libraryApi.patch(item.id, { unavailable: false }).then(merge),
      ),
    });
  }
  items.push(
    { kind: "divider" },
    { label: "Ask Assistant", icon: icons.chat, onSelect: () => navigate(`/chat?items=${item.id}`) },
    { kind: "divider" },
    {
      label: "Archive in Keptwise",
      icon: icons.trash,
      danger: true,
      onSelect: () =>
        void attempt(() => patch({ deleted: true }), "Moved to the Keptwise Archive.", () => patch({ deleted: false })),
    },
  );
  return items;
}

/** The menu when several picked saves are right-clicked together. */
export function selectionMenuItems(ids: number[], { onDone, onClear }: { onDone: () => void; onClear: () => void }): MenuItem[] {
  const many = `${ids.length} saves`;
  const bulk = (action: "delete" | "restore", done: string, undo?: "restore") =>
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
    { label: `Archive ${many}`, icon: icons.trash, danger: true, hint: "to the Archive", onSelect: () => void bulk("delete", `Moved ${many} to the Keptwise Archive.`, "restore") },
    { kind: "divider" },
    { label: "Clear the selection", icon: icons.close, hint: "Esc", onSelect: onClear },
  ];
}
