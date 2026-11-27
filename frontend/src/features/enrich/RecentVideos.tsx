// The videos processed most recently: thumbnail, details, how long it took,
// and the start of the transcript (or why there isn't one).
import { SaveControls } from "../library/SaveControls";
import { Badge, Card } from "../../components/ui";
import { formatDuration, type RecentVideo } from "./enrichApi";

export default function RecentVideos({ videos, embedded = false }: { videos: RecentVideo[]; embedded?: boolean }) {
  if (videos.length === 0) return null;
  return (
    <section>
      {!embedded && <h2 className="text-lg font-semibold tracking-tight">Recently done</h2>}
      <ul className="mt-3 space-y-3">
        {videos.map((video) => (
          <li key={video.id}>
            <VideoRow video={video} />
          </li>
        ))}
      </ul>
    </section>
  );
}

function VideoRow({ video }: { video: RecentVideo }) {
  const duration = formatDuration(video.duration_s);
  const failed = video.status === "failed";
  return (
    <Card className="group flex gap-4 p-4">
      <div className="h-24 w-16 shrink-0 overflow-hidden rounded-lg bg-zinc-100 dark:bg-zinc-800">
        {video.has_thumbnail && (
          <img src={`/api/items/${video.id}/thumbnail`} alt="" className="h-full w-full object-cover" loading="lazy" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
      <SaveControls id={video.id} title={video.title ?? video.url} />
          <StatusBadge video={video} />
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {[video.platform_name, video.author ? `@${video.author.replace(/^@/, "")}` : null, duration]
              .filter(Boolean)
              .join(" · ")}
          </span>
          {video.seconds != null && (
            <span className="ml-auto text-xs tabular-nums text-zinc-400" title="How long the app took for this video">
              took {video.seconds.toFixed(1)} s
            </span>
          )}
        </div>
        <a
          href={video.url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 block truncate font-medium hover:underline"
          title={video.title ?? video.url}
        >
          {video.title ?? video.url}
        </a>
        {failed || video.error ? (
          <p className={`mt-1 text-sm ${failed ? "text-red-700 dark:text-red-300" : "text-amber-700 dark:text-amber-300"}`}>
            {video.error}
          </p>
        ) : video.no_speech ? (
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">The speech model didn't detect any words.</p>
        ) : (
          video.transcript_preview && (
            <p className="mt-1 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-300">“{video.transcript_preview}”</p>
          )
        )}
      </div>
    </Card>
  );
}

function StatusBadge({ video }: { video: RecentVideo }) {
  if (video.status === "failed") return <Badge tone="red">Couldn't read</Badge>;
  if (video.error) return <Badge tone="amber">Details only</Badge>;
  if (video.no_speech) return <Badge>No speech detected</Badge>;
  return <Badge tone="green">Transcribed</Badge>;
}
