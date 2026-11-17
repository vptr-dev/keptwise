// Helpers for the sidebar's pages (their saved order), kept apart from the
// components so they're easy to test.

/** Put the sidebar pages in the saved order, leaving out hidden ones. */
export function arrangeNav<T extends { path: string }>(items: T[], order: string[], hidden: string[], keep = "/settings"): T[] {
  const known = new Map(items.map((item) => [item.path, item]));
  const ordered = order.flatMap((path) => (known.has(path) ? [known.get(path) as T] : []));
  const rest = items.filter((item) => !order.includes(item.path));
  return [...ordered, ...rest].filter((item) => item.path === keep || !hidden.includes(item.path));
}

/** The order after dragging page `from` onto page `to` (before or after it). */
export function movedNav(paths: string[], from: string, to: string, after: boolean): string[] {
  if (from === to) return paths;
  const rest = paths.filter((p) => p !== from);
  const at = rest.indexOf(to);
  if (at < 0) return paths;
  rest.splice(at + (after ? 1 : 0), 0, from);
  return rest;
}
