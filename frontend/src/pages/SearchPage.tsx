// Search results for the words in the search bar (#/search?q=...).
// "Your words" results contain the words (highlighted, with where they
// are); "Similar idea" results say the same thing in other words.
import { useCallback, useEffect, useState } from "react";

import JobCard from "../components/JobCard";
import { Button, Card, Notice } from "../components/ui";
import ItemPanel from "../features/search/ItemPanel";
import ResultCard from "../features/search/ResultCard";
import SearchBar from "../features/search/SearchBar";
import { searchApi, type IndexStatus, type SearchMode, type SearchResponse } from "../features/search/searchApi";
import { errorText } from "../lib/api";
import { isActive, useJobFinished, useJobs } from "../lib/jobs";
import { navigate, useRoute } from "../lib/router";

const MODES: { id: SearchMode; label: string }[] = [
  { id: "both", label: "Everything" },
  { id: "words", label: "Your words" },
  { id: "captions", label: "Captions" },
  { id: "similar", label: "Similar ideas" },
];

export default function SearchPage() {
  const route = useRoute();
  const query = (route.query.get("q") ?? "").trim();
  const [mode, setMode] = useState<SearchMode>("both");
  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const jobs = useJobs();
  const indexJob = jobs.find((job) => job.kind === "search_index" && isActive(job)) ?? null;

  const loadStatus = useCallback(() => {
    searchApi.status().then(setStatus).catch(() => undefined);
  }, []);
  useEffect(loadStatus, [loadStatus]);

  const [refresh, setRefresh] = useState(0);
  useJobFinished(["search_index"], () => {
    loadStatus();
    setRefresh((n) => n + 1);
  });

  useEffect(() => {
    if (!query) {
      setData(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    searchApi
      .search(query, mode, controller.signal)
      .then((response) => setData(response))
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorText(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [query, mode, refresh]);

  const results = data?.query === query ? data.results : [];
  const openResult = results.find((r) => r.item.id === openId);

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-8 py-10">
      <SearchBar />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{query ? `Results for “${query}”` : "Search"}</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Searches what's said in your videos, their captions and the AI's notes. Similar ideas are found on this
            PC, even when other words are used.
          </p>
        </div>
        {query && (
          <Button variant="secondary" onClick={() => navigate(`/chat?${new URLSearchParams({ q: query })}`)}>
            Ask about this
          </Button>
        )}
      </header>

      <SimilarStatus status={status} jobRunning={indexJob !== null} onStart={() => searchApi.startIndex().then(setStatus)} />
      {indexJob && <JobCard job={indexJob} name="similar-search job" />}

      {!query ? (
        <Card>
          <p className="text-sm text-zinc-600 dark:text-zinc-300">
            Type in the search bar above. Try a dish, a place, a product or an idea, e.g. “pasta”, “London” or
            “how to study”.
          </p>
        </Card>
      ) : (
        <>
          <div role="tablist" aria-label="Which results" className="flex gap-1 rounded-xl bg-zinc-100 p-1 text-sm dark:bg-zinc-900">
            {MODES.map((m) => (
              <button
                key={m.id}
                role="tab"
                type="button"
                aria-selected={mode === m.id}
                onClick={() => setMode(m.id)}
                className={`flex-1 rounded-lg px-3 py-1.5 font-medium transition ${
                  mode === m.id
                    ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100"
                    : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {error && <Notice tone="error">{error}</Notice>}
          {loading && results.length === 0 && <p className="text-sm text-zinc-500">Searching…</p>}
          {!loading && !error && data?.query === query && results.length === 0 && (
            <Card>
              <p className="font-medium">Nothing found for “{query}”.</p>
              <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
                Try other words. Only videos with a transcript, a caption or AI notes can be found; make transcripts on
                the Transcripts screen.
              </p>
            </Card>
          )}
          {results.length > 0 && (
            <p className="text-sm text-zinc-500 dark:text-zinc-400" data-testid="result-count">
              {results.length === 1 ? "1 video" : `${results.length} videos`}
            </p>
          )}
          <div className="space-y-3">
            {results.map((result) => (
              <ResultCard key={result.item.id} item={result.item} result={result} onOpen={setOpenId} />
            ))}
          </div>
        </>
      )}

      {openId !== null && (
        <ItemPanel itemId={openId} words={openResult?.words ?? []} onClose={() => setOpenId(null)} />
      )}
    </div>
  );
}

function SimilarStatus({
  status,
  jobRunning,
  onStart,
}: {
  status: IndexStatus | null;
  jobRunning: boolean;
  onStart: () => void;
}) {
  const [closed, setClosed] = useState(false);
  if (!status || jobRunning || closed) return null;
  if (!status.model_ready) {
    return (
      <Notice onClose={() => setClosed(true)}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>
            Finding similar ideas needs a small search model ({Math.round(status.model_bytes / 1e6)} MB, downloaded
            once). Searching for your exact words works already.
          </span>
          <Button size="sm" onClick={onStart}>
            Turn on similar search
          </Button>
        </div>
      </Notice>
    );
  }
  if (status.waiting > 0) {
    return (
      <Notice onClose={() => setClosed(true)}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span>
            {status.waiting === 1 ? "1 video isn't" : `${status.waiting} videos aren't`} ready for similar search yet.
          </span>
          <Button size="sm" variant="secondary" onClick={onStart}>
            Get them ready
          </Button>
        </div>
      </Notice>
    );
  }
  return null;
}
