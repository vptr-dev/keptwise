// Small shared building blocks so every screen looks the same.
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

const VARIANTS: Record<Variant, string> = {
  primary: "kw-btn-primary bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-indigo-400",
  secondary:
    "border border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800",
  danger: "bg-red-600 text-white hover:bg-red-500",
  ghost: "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" }) {
  const sizing = size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-2 text-sm";
  return (
    <button
      type="button"
      className={`inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap kw-btn rounded-lg font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-500 disabled:cursor-not-allowed disabled:opacity-60 ${sizing} ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section
      className={`kw-glass rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 ${className}`}
    >
      {children}
    </section>
  );
}

type Tone = "info" | "success" | "warning" | "error";

const TONES: Record<Tone, string> = {
  info: "bg-indigo-50 text-indigo-900 dark:bg-indigo-950/60 dark:text-indigo-200",
  success: "bg-emerald-50 text-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-200",
  warning: "bg-amber-50 text-amber-900 dark:bg-amber-950/60 dark:text-amber-200",
  error: "bg-red-50 text-red-900 dark:bg-red-950/60 dark:text-red-200",
};

export function Notice({
  tone = "info",
  children,
  onClose,
  closeLabel = "Close",
}: {
  tone?: Tone;
  children: ReactNode;
  onClose?: () => void; // shows a × button
  closeLabel?: string;
}) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`relative rounded-xl px-4 py-3 text-sm ${onClose ? "pr-10" : ""} ${TONES[tone]}`}
    >
      {children}
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label={closeLabel}
          title={closeLabel}
          className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-md opacity-60 hover:bg-black/5 hover:opacity-100 dark:hover:bg-white/10"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "green" | "amber" | "indigo" | "red" }) {
  const tones = {
    neutral: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
    green: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200",
    amber: "bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200",
    indigo: "bg-indigo-100 text-indigo-800 dark:bg-indigo-900/60 dark:text-indigo-200",
    red: "bg-red-100 text-red-800 dark:bg-red-900/60 dark:text-red-200",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {children}
    </span>
  );
}

export const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100";

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{label}</span>
      {children}
      {hint && <span className="kw-tip block text-xs text-zinc-500 dark:text-zinc-400">{hint}</span>}
    </label>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-xl bg-zinc-100 p-1 dark:bg-zinc-800">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
            value === option.value
              ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-950 dark:text-white"
              : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "unknown";
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
  return `${Math.max(1, Math.round(bytes / 1e3))} KB`;
}
