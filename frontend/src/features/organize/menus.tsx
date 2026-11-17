// What the right-click menus on a collection and on a tag offer.
import { IconPicker } from "./collectionIcons";
import type { MenuItem } from "../../components/ContextMenu";
import type { Ask } from "../../components/Dialog";
import { toast } from "../../components/Toasts";
import { icons } from "../../components/icons";
import { errorText } from "../../lib/api";
import { navigate } from "../../lib/router";
import { sortingApi, type Collection, type Space } from "../sorting/sortingApi";
import { announceChange, organizeApi, type Tag } from "./organizeApi";

async function run(task: () => Promise<unknown>, done?: string) {
  try {
    await task();
    if (done) toast(done);
  } catch (e) {
    toast(errorText(e), { tone: "error" });
  }
  announceChange();
}

function assistant(tool: string, label: string, target: string, empty: boolean): MenuItem {
  return { label, icon: icons.sparkle, disabled: empty, onSelect: () => navigate(`/chat?tool=${tool}&${target}`) };
}

/** Everywhere a collection could be moved: the top of each space, or inside any collection that isn't inside it. */
export function moveTargets(moving: Collection[], all: Collection[], spaces: Space[]): { value: string; label: string }[] {
  const blocked = new Set<number>();
  for (const one of moving) {
    blocked.add(one.id);
    // everything inside it comes right after it in the list, deeper than it
    const at = all.findIndex((c) => c.id === one.id);
    for (let i = at + 1; i < all.length && all[i].depth > one.depth; i++) blocked.add(all[i].id);
  }
  const options: { value: string; label: string }[] = [];
  for (const space of spaces) {
    options.push({ value: `space:${space.id}`, label: spaces.length > 1 ? `${space.name} (top of this space)` : "The top level" });
    for (const c of all) {
      if (c.space_id === space.id && !blocked.has(c.id)) {
        options.push({ value: `in:${c.id}`, label: `${"\u00a0\u00a0".repeat(c.depth + 1)}${c.name}` });
      }
    }
  }
  return options;
}

/** Turn a moveTargets value into what the backend wants. */
export function targetOf(value: string): { parent_id: number | null; space_id?: number } {
  const [kind, id] = value.split(":");
  return kind === "in" ? { parent_id: Number(id) } : { parent_id: null, space_id: Number(id) };
}

export function collectionMenuItems(
  collection: Collection,
  { all, spaces = [], ask, onDeleted, extra = [] }: { all: Collection[]; spaces?: Space[]; ask: Ask; onDeleted?: () => void; extra?: MenuItem[] },
): MenuItem[] {
  const change = (update: Parameters<typeof organizeApi.changeCollection>[1], done?: string) =>
    run(() => organizeApi.changeCollection(collection.id, update), done);
  // Its neighbours: the collections next to it, inside the same one.
  const siblings = all.filter((c) => c.space_id === collection.space_id && c.parent_id === collection.parent_id);
  const index = siblings.findIndex((c) => c.id === collection.id);
  const others = all.filter((c) => c.id !== collection.id);
  const place = (to: number) => run(() => organizeApi.placeCollection(collection.id, collection.parent_id, to));
  const parent = all.find((c) => c.id === collection.parent_id);
  const empty = collection.count === 0;
  const target = `collection=${collection.id}`;
  return [
    ...extra,
    ...(extra.length ? [{ kind: "divider" } as MenuItem] : []),
    { label: "Open", icon: icons.folder, onSelect: () => navigate(`/collections/${collection.id}`) },
    { label: "Show in the Library", icon: icons.library, onSelect: () => navigate(`/library?collection_id=${collection.id}`) },
    { kind: "divider" },
    {
      label: "New collection inside…",
      icon: icons.plus,
      onSelect: async () => {
        const name = await ask.text({ title: `New collection in “${collection.name}”`, label: "Name", confirm: "Add" });
        if (name) run(() => organizeApi.createCollection(name, collection.id), `Added “${name}”.`);
      },
    },
    {
      label: "Move to…",
      icon: icons.folder,
      onSelect: async () => {
        const where = await ask.pick({
          title: `Move “${collection.name}”`,
          label: "Put it in",
          options: moveTargets([collection], all, spaces),
          confirm: "Move",
          hint: "Everything inside it moves with it.",
        });
        if (where) {
          const target = targetOf(where);
          run(() => organizeApi.placeCollection(collection.id, target.parent_id, 10000, target.space_id), "Moved.");
        }
      },
    },
    {
      label: "Move up a level",
      icon: icons.up,
      disabled: !parent,
      onSelect: () => run(() => organizeApi.placeCollection(collection.id, parent?.parent_id ?? null, 10000), "Moved up a level."),
    },
    { kind: "divider" },
    {
      label: "Rename…",
      icon: icons.pencil,
      onSelect: async () => {
        const name = await ask.text({ title: "Rename collection", label: "Name", value: collection.name });
        if (name && name !== collection.name) change({ name }, `Renamed to “${name}”.`);
      },
    },
    {
      label: "What goes in it…",
      icon: icons.list,
      onSelect: async () => {
        const about = await ask.text({
          title: `What goes in “${collection.name}”?`,
          label: "A short note. The AI reads it when it sorts.",
          value: collection.description ?? "",
          maxLength: 300,
        });
        if (about !== null) change({ description: about }, "Saved.");
      },
    },
    { kind: "colors", label: "Colour", value: collection.color, onPick: (color) => change({ color }) },
    {
      kind: "panel",
      label: "Icon…",
      icon: icons.grid,
      title: `Icon for “${collection.name}”`,
      width: 250,
      panel: (close) => (
        <IconPicker
          value={collection.icon}
          onPick={(icon) => {
            change({ icon: icon ?? "" });
            close();
          }}
        />
      ),
    },
    {
      label: "The AI can sort saves into it",
      checked: collection.ai_allowed,
      onSelect: () => change({ ai_allowed: !collection.ai_allowed }),
    },
    { kind: "divider" },
    { label: "Move to the top", icon: icons.up, disabled: index <= 0, onSelect: () => place(0) },
    { label: "Move earlier", icon: icons.up, disabled: index <= 0, onSelect: () => place(index - 1) },
    { label: "Move later", icon: icons.down, disabled: index < 0 || index >= siblings.length - 1, onSelect: () => place(index + 1) },
    { kind: "divider" },
    { kind: "heading", label: "AI Assistant" },
    assistant("summary", "Summarise it", target, empty),
    assistant("plan", "Make a plan from it", target, empty),
    assistant("shopping", "Shopping or packing list", target, empty),
    assistant("compare", "Help me choose", target, empty),
    { kind: "divider" },
    {
      label: "Merge into…",
      icon: icons.link,
      disabled: others.length === 0,
      onSelect: async () => {
        const into = await ask.pick({
          title: `Merge “${collection.name}”`,
          label: "Move all of its saves into",
          options: others.map((c) => ({ value: String(c.id), label: `${c.name} (${c.count})` })),
          confirm: "Merge",
          hint: `Then “${collection.name}” is deleted.`,
        });
        if (into) {
          const name = others.find((c) => c.id === Number(into))?.name ?? "";
          await run(() => organizeApi.mergeCollection(collection.id, Number(into)), `Merged into “${name}”.`);
          onDeleted?.();
        }
      },
    },
    {
      label: "Delete…",
      icon: icons.trash,
      danger: true,
      onSelect: async () => {
        const sure = await ask.confirm({
          title: `Delete “${collection.name}”?`,
          body: "Its saves stay in the app; they just won't be in this collection any more. Collections inside it move up a level.",
          confirm: "Delete",
          danger: true,
        });
        if (sure) {
          await run(() => sortingApi.deleteCollection(collection.id), `Deleted “${collection.name}”.`);
          onDeleted?.();
        }
      },
    },
  ];
}

export function tagMenuItems(tag: Tag, { all, ask, extra = [] }: { all: Tag[]; ask: Ask; extra?: MenuItem[] }): MenuItem[] {
  const others = all.filter((t) => t.id !== tag.id).sort((a, b) => a.name.localeCompare(b.name));
  const target = `tag=${encodeURIComponent(tag.name)}`;
  const empty = tag.count === 0;
  return [
    ...extra,
    ...(extra.length ? [{ kind: "divider" } as MenuItem] : []),
    { label: "Show its saves", icon: icons.library, onSelect: () => navigate(`/library?tags=${encodeURIComponent(tag.name)}`) },
    {
      label: "Rename…",
      icon: icons.pencil,
      onSelect: async () => {
        const name = await ask.text({
          title: `Rename #${tag.name}`,
          label: "Name",
          value: tag.name,
          maxLength: 40,
          hint: "Typing the name of another tag merges the two.",
        });
        if (name && name !== tag.name) run(() => organizeApi.changeTag(tag.id, { name }), `Renamed to #${name.replace(/^#/, "").toLowerCase()}.`);
      },
    },
    { kind: "colors", label: "Colour", value: tag.color, onPick: (color) => run(() => organizeApi.changeTag(tag.id, { color })) },
    { kind: "divider" },
    { kind: "heading", label: "AI Assistant" },
    assistant("summary", "Summarise these saves", target, empty),
    assistant("plan", "Make a plan from them", target, empty),
    assistant("shopping", "Shopping or packing list", target, empty),
    { kind: "divider" },
    {
      label: "Merge into…",
      icon: icons.link,
      disabled: others.length === 0,
      onSelect: async () => {
        const into = await ask.pick({
          title: `Merge #${tag.name}`,
          label: "Put its saves under",
          options: others.map((t) => ({ value: String(t.id), label: `#${t.name} (${t.count})` })),
          confirm: "Merge",
          hint: `Then #${tag.name} is gone.`,
        });
        const other = others.find((t) => t.id === Number(into));
        if (other) run(() => organizeApi.mergeTags([tag.id, other.id], other.name), `Merged into #${other.name}.`);
      },
    },
    {
      label: "Delete…",
      icon: icons.trash,
      danger: true,
      onSelect: async () => {
        const sure = await ask.confirm({
          title: `Delete #${tag.name}?`,
          body: `It comes off ${tag.count === 1 ? "the 1 save" : `all ${tag.count.toLocaleString()} saves`} that have it. The saves stay.`,
          confirm: "Delete",
          danger: true,
        });
        if (sure) run(() => organizeApi.deleteTag(tag.id), `Deleted #${tag.name}.`);
      },
    },
  ];
}
