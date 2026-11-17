// Text with the matching words marked in yellow.
import type { Segment } from "./searchApi";

export default function Highlighted({ segments }: { segments: Segment[] }) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.hit ? (
          <mark key={index} className="rounded bg-amber-200 px-0.5 text-zinc-900 dark:bg-amber-400/40 dark:text-amber-50">
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}
