// "How do I get my export?" steps for each platform, folded away until needed.
import { GUIDES } from "./guides";

export default function PlatformGuides() {
  return (
    <section>
      <h2 className="text-lg font-semibold tracking-tight">How to get your export</h2>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        Each platform lets you download a copy of your data. Ask for JSON format where you can. Menu names may differ
        slightly on your phone.
      </p>
      <div className="mt-4 grid items-start gap-3 md:grid-cols-2">
        {GUIDES.map((guide) => (
          <details
            key={guide.platform}
            className="group rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between font-medium">
              {guide.name}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="h-4 w-4 text-zinc-400 transition group-open:rotate-180" aria-hidden="true">
                <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </summary>
            <ol className="mt-3 list-decimal space-y-1.5 pl-5 text-sm text-zinc-700 dark:text-zinc-300">
              {guide.steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
              <li>Drag the zip you downloaded onto this page.</li>
            </ol>
            <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">{guide.wait}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
