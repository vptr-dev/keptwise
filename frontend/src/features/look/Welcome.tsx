// The first time Keptwise opens: make it yours (name, light or dark, accent
// colour, text size, where it opens) in a few small steps, then bring your
// saves in. Every choice shows straight away and can be changed later in
// Settings -> Appearance. "Skip" keeps the standard look.
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

import Logo from "../../components/Logo";
import { icons } from "../../components/icons";
import { Button, Segmented, inputClass } from "../../components/ui";
import { navigate } from "../../lib/router";
import { START_PAGE_LABELS, TEXT_SIZE_LABELS, THEME_LABELS, type Look, type StartPage, type ThemeChoice } from "../../lib/theme";
import { AccentSwatches } from "./AppearanceSettings";
import WorkflowControls from "../sorting/WorkflowControls";

const STEPS = ["Hello", "Look", "Layout", "Workflow", "Ready"] as const;

export default function Welcome({
  look,
  onChange,
  onTheme,
  cloud = false,
}: {
  look: Look;
  onChange: (change: Partial<Look>) => void;
  onTheme: (theme: ThemeChoice) => void;
  cloud?: boolean;
}) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState(look.name);
  const [savingWorkflow, setSavingWorkflow] = useState(false);
  const finish = (then?: string) => {
    onChange({ name: name.trim().slice(0, 40), welcomed: true });
    if (then) navigate(then);
  };
  const next = () => {
    if (step === 0) onChange({ name: name.trim().slice(0, 40) });
    setStep(step + 1);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !savingWorkflow) finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }); // eslint-disable-line react-hooks/exhaustive-deps

  return createPortal(
    <div className="kw-fade fixed inset-0 z-[80] flex items-center justify-center bg-zinc-950/30 p-6 backdrop-blur-sm">
      <section
        role="dialog"
        aria-modal="true"
        aria-label="Set up Keptwise"
        className="kw-rise kw-glass-pop flex max-h-full w-full overflow-y-auto max-w-lg flex-col rounded-3xl border border-zinc-200 bg-white p-8 shadow-2xl dark:border-zinc-700 dark:bg-zinc-900"
      >
        <div className="mb-6 flex items-center justify-between">
          <ol className="flex gap-1.5" aria-label="Steps">
            {STEPS.map((label, index) => (
              <li
                key={label}
                aria-current={index === step ? "step" : undefined}
                title={label}
                className={`h-1.5 rounded-full transition-all duration-300 ${index === step ? "w-6 bg-indigo-600 dark:bg-indigo-400" : index < step ? "w-1.5 bg-indigo-600/50 dark:bg-indigo-400/50" : "w-1.5 bg-zinc-300 dark:bg-zinc-700"}`}
              />
            ))}
          </ol>
          {step < STEPS.length - 1 && (
            <button type="button" onClick={() => finish()} disabled={savingWorkflow} className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white">
              Skip
            </button>
          )}
        </div>

        <div key={step} className="kw-in-right min-h-[17rem]">
          {step === 0 && (
            <div className="space-y-6">
              <Logo className="h-16 w-16" />
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">Welcome to Keptwise</h1>
                <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                  Everything you save on TikTok, YouTube, Instagram and Facebook, in one place on this PC, sorted and
                  searchable. First, make it yours. It takes a minute.
                </p>
              </div>
              <label className="block space-y-1.5">
                <span className="text-sm font-medium">What should we call you?</span>
                <input
                  autoFocus
                  className={inputClass}
                  placeholder="Your name (optional)"
                  maxLength={40}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && next()}
                />
              </label>
            </div>
          )}

          {step === 1 && (
            <div className="space-y-6">
              <Heading title={name.trim() ? `How should it look, ${name.trim()}?` : "How should it look?"} text="Every choice shows straight away." />
              <Choice label="Light or dark">
                <Segmented
                  label="Theme"
                  value={look.theme}
                  onChange={onTheme}
                  options={(["light", "dark", "system"] as const).map((value) => ({ value, label: THEME_LABELS[value] }))}
                />
              </Choice>
              <Choice label="Accent colour" hint="Buttons, links and the logo take this colour. Default is plain black and white.">
                <AccentSwatches value={look.accent} onChange={(accent) => onChange({ accent })} />
              </Choice>
              <Choice label="Text size">
                <Segmented
                  label="Text size"
                  value={look.text_size}
                  onChange={(text_size) => onChange({ text_size })}
                  options={(["small", "normal", "large"] as const).map((value) => ({ value, label: TEXT_SIZE_LABELS[value] }))}
                />
              </Choice>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-6">
              <Heading title="How should it open?" text="You can drag the pages in the sidebar into any order later." />
              <Choice label="Open Keptwise on">
                <div role="radiogroup" aria-label="Open Keptwise on" className="flex flex-wrap gap-2">
                  {(Object.keys(START_PAGE_LABELS) as StartPage[]).map((page) => (
                    <button
                      key={page}
                      type="button"
                      role="radio"
                      aria-checked={look.start_page === page}
                      onClick={() => onChange({ start_page: page })}
                      className={`kw-btn rounded-full border px-3.5 py-1.5 text-sm font-medium ${
                        look.start_page === page
                          ? "border-indigo-600 bg-indigo-600 text-white"
                          : "border-zinc-200 text-zinc-600 hover:border-zinc-300 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-300 dark:hover:text-white"
                      }`}
                    >
                      {START_PAGE_LABELS[page]}
                    </button>
                  ))}
                </div>
              </Choice>
              <Toggle
                checked={look.compact_sidebar}
                onChange={(compact_sidebar) => onChange({ compact_sidebar })}
                label="Slim sidebar"
                hint="Only the icons, for more room."
              />
              <Toggle
                checked={look.card_actions}
                onChange={(card_actions) => onChange({ card_actions })}
                label="Quick buttons on saves"
                hint="Point at a save to tag it, file it or add it to a plan."
              />
            </div>
          )}

          {step === 3 && (
            <div className="space-y-5">
              <Heading title="How much should Keptwise do?" text="Choose what to automate. Start with suggestions and review them yourself, or let Keptwise file and tag confident matches." />
              <WorkflowControls cloud={cloud} onSaving={setSavingWorkflow} />
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Change these choices later in Settings → Workflow.</p>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-6">
              <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 p-3.5 text-white dark:bg-indigo-500 dark:text-zinc-900">
                {icons.check}
              </span>
              <Heading
                title={name.trim() ? `All set, ${name.trim()}` : "All set"}
                text="Next, bring in your saves: ask TikTok, YouTube, Instagram or Facebook for your data, then drop the file on the Import page. Your library is stored on this PC."
              />
            </div>
          )}
        </div>

        <div className="mt-8 flex items-center justify-between gap-3">
          {step > 0 ? (
            <Button variant="ghost" disabled={savingWorkflow} onClick={() => setStep(step - 1)}>
              Back
            </Button>
          ) : (
            <span />
          )}
          {step < STEPS.length - 1 ? (
            <Button disabled={savingWorkflow} onClick={next}>{step === 0 ? "Make it mine" : "Next"}</Button>
          ) : (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => finish()}>
                Look around first
              </Button>
              <Button onClick={() => finish("/import")}>Import my saves</Button>
            </div>
          )}
        </div>
      </section>
    </div>,
    document.body,
  );
}

function Heading({ title, text }: { title: string; text: string }) {
  return (
    <div>
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">{text}</p>
    </div>
  );
}

function Choice({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {hint && <p className="text-xs text-zinc-500 dark:text-zinc-400">{hint}</p>}
      </div>
      {children}
    </div>
  );
}

function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (on: boolean) => void; label: string; hint: string }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4 rounded-2xl border border-zinc-200 px-4 py-3 dark:border-zinc-700">
      <span className="text-sm">
        <span className="font-medium">{label}</span>
        <span className="block text-zinc-500 dark:text-zinc-400">{hint}</span>
      </span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4 accent-indigo-600" />
    </label>
  );
}
