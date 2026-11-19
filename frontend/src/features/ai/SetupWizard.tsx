// First-run wizard: "Free, on this PC" or "Cloud, with your API key",
// then set it up and test the connection.
import { useState } from "react";

import { Button, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { aiApi, type AiOverview } from "./aiApi";
import AiSettings from "./AiSettings";

type Step = "choose" | "local" | "cloud";

export default function SetupWizard({
  overview,
  onChange,
  onFinish,
}: {
  overview: AiOverview;
  onChange: (overview: AiOverview) => void;
  onFinish: () => void;
}) {
  const [step, setStep] = useState<Step>("choose");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (problem) {
      setError(errorText(problem));
    } finally {
      setBusy(false);
    }
  }

  const finish = () => save(async () => {
    onChange(await aiApi.setupDone());
    onFinish();
  });

  const choose = (kind: "local" | "cloud") => save(async () => {
    if (overview.current_kind !== kind) {
      onChange(await aiApi.setCurrent(kind === "local" ? "ollama" : "anthropic"));
    }
    setStep(kind);
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/60 p-6 backdrop-blur-sm">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="wizard-title"
        className="max-h-full w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-8 shadow-xl dark:bg-zinc-900"
      >
        <h2 id="wizard-title" className="text-2xl font-semibold tracking-tight">
          Welcome to Keptwise
        </h2>
        <p className="mt-1 text-zinc-600 dark:text-zinc-400">
          Choose an AI for notes and suggestions, or skip to use your library and organise saves yourself.
        </p>

        {error && <div className="mt-4"><Notice tone="error">{error}</Notice></div>}
        {step === "choose" ? (
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <ChoiceCard
              title="Free, on this PC"
              body="Uses Ollama. Nothing leaves your computer. Needs a one-time download of about 8 GB."
              disabled={busy}
              onClick={() => void choose("local")}
            />
            <ChoiceCard
              title="Cloud, with your API key"
              body="Claude, OpenAI, Gemini or OpenRouter. Your provider may charge when you choose to run an AI task."
              disabled={busy}
              onClick={() => void choose("cloud")}
            />
          </div>
        ) : (
          <div className="mt-6 space-y-6">
            <AiSettings overview={overview} onChange={onChange} only={step} />
            <div className="flex justify-between">
              <Button variant="ghost" disabled={busy} onClick={() => setStep("choose")}>
                Back
              </Button>
              <Button disabled={busy} onClick={finish}>Finish</Button>
            </div>
          </div>
        )}

        <div className="mt-6 text-right">
          <button type="button" className="text-sm text-zinc-500 hover:underline" disabled={busy} onClick={finish}>
            Skip for now
          </button>
        </div>
      </div>
    </div>
  );
}

function ChoiceCard({ title, body, disabled, onClick }: { title: string; body: string; disabled: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="rounded-2xl border border-zinc-200 p-5 text-left transition hover:border-indigo-500 hover:bg-indigo-50/50 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:border-zinc-700 dark:hover:bg-indigo-950/30"
    >
      <p className="text-lg font-medium">{title}</p>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{body}</p>
    </button>
  );
}
