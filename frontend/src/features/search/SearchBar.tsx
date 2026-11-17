// The search box at the top of the Search screen (#/search?q=...): results
// follow as you type. From anywhere else, Ctrl+K opens the command centre.
import { useEffect, useRef, useState } from "react";

import { icons } from "../../components/icons";
import { navigate, useRoute } from "../../lib/router";

const TYPING_PAUSE_MS = 300;

/** Change the address without adding a Back step for every letter typed. */
function replaceSearch(q: string) {
  const target = `#/search?${new URLSearchParams({ q })}`;
  if (window.location.hash === target) return;
  window.history.replaceState(null, "", target);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

export default function SearchBar() {
  const route = useRoute();
  const onSearchPage = route.parts[0] === "search";
  const routeQuery = onSearchPage ? route.query.get("q") ?? "" : "";
  const [text, setText] = useState(routeQuery);
  const inputRef = useRef<HTMLInputElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const pushed = useRef<string | null>(null); // the last search this box put in the address

  // Follow the address (e.g. Back, or a link to a search). Leaving the
  // Search screen empties the box, so it never shows an old search.
  useEffect(() => {
    if (onSearchPage && routeQuery === pushed.current) return; // our own change: keep what's typed since
    setText(onSearchPage ? routeQuery : "");
  }, [onSearchPage, routeQuery]);

  function change(value: string) {
    setText(value);
    window.clearTimeout(timer.current);
    if (!onSearchPage) return; // elsewhere, wait for Enter
    timer.current = window.setTimeout(() => {
      pushed.current = value;
      replaceSearch(value);
    }, TYPING_PAUSE_MS);
  }

  function submit() {
    window.clearTimeout(timer.current);
    pushed.current = text;
    if (onSearchPage) replaceSearch(text);
    else navigate(`/search?${new URLSearchParams({ q: text })}`);
  }

  return (
    <form
      role="search"
      className="relative w-full"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <span className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400">{icons.search}</span>
      <input
        ref={inputRef}
        type="search"
        value={text}
        onChange={(event) => change(event.target.value)}
        onKeyDown={(event) => event.key === "Escape" && inputRef.current?.blur()}
        placeholder="Search your saves: captions, transcripts and notes…"
        aria-label="Search your saves"
        className="w-full rounded-xl border border-zinc-200 bg-white/70 py-2.5 pl-9 pr-3 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100 dark:focus:bg-zinc-950"
      />
    </form>
  );
}
