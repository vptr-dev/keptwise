// What a screen shows when there's nothing in it yet: a picture, a line
// saying why, and the button that gets things going.
import type { ReactNode } from "react";

export default function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-zinc-300 bg-white/60 px-6 py-14 text-center dark:border-zinc-700 dark:bg-zinc-900/40">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 p-3 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-300">
        {icon}
      </span>
      <h2 className="mt-4 text-base font-semibold">{title}</h2>
      {children && <div className="mt-1.5 max-w-md text-sm text-zinc-500 dark:text-zinc-400">{children}</div>}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}
