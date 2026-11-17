// A thin progress bar. Without a total it shows a moving "busy" bar.
export default function ProgressBar({
  done,
  total,
  label,
}: {
  done: number;
  total: number;
  label?: string;
}) {
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null;
  return (
    <div
      role="progressbar"
      aria-label={label ?? "Progress"}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent ?? undefined}
      className="h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800"
    >
      <div
        className={`h-full rounded-full bg-indigo-600 transition-[width] duration-300 ${
          percent === null ? "w-1/3 animate-pulse" : ""
        }`}
        style={percent === null ? undefined : { width: `${percent}%` }}
      />
    </div>
  );
}
