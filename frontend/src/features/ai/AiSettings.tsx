// The AI section of Settings: switch between Local and Cloud at any time,
// pick the provider and model, and test the connection.
import { useCallback, useState } from "react";

import { Button, Field, Notice, Segmented, inputClass } from "../../components/ui";
import { errorText } from "../../lib/api";
import { aiApi, type AiOverview, type TestResult } from "./aiApi";
import OllamaPanel from "./OllamaPanel";
import ProviderPanel from "./ProviderPanel";

type Kind = "local" | "cloud";

export default function AiSettings({
  overview,
  onChange,
  only,
}: {
  overview: AiOverview;
  onChange: (overview: AiOverview) => void;
  only?: Kind; // the setup wizard shows just one side
}) {
  const [test, setTest] = useState<TestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const kind: Kind = only ?? overview.current_kind;
  const choices = overview.providers.filter((p) => p.kind === kind);
  const current = overview.providers.find((p) => p.id === overview.current) ?? choices[0];

  const update = useCallback(
    async (action: () => Promise<AiOverview>) => {
      setError(null);
      setTest(null);
      try {
        onChange(await action());
      } catch (err) {
        setError(errorText(err));
      }
    },
    [onChange],
  );

  const switchKind = (next: Kind) => {
    if (next === overview.current_kind) return;
    // Remember-friendly defaults: Ollama for local; a cloud provider with a saved key, else Claude.
    const target =
      next === "local"
        ? "ollama"
        : (overview.providers.find((p) => p.kind === "cloud" && p.key_saved)?.id ?? "anthropic");
    void update(() => aiApi.setCurrent(target));
  };

  const setOllamaModel = useCallback(
    (model: string) => void update(() => aiApi.setModel("ollama", model)),
    [update],
  );

  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      setTest(await aiApi.test(current.id));
    } catch (err) {
      setTest({ ok: false, message: errorText(err) });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-5">
      {!only && (
        <div className="space-y-2">
          <Segmented
            label="Where the AI runs"
            value={overview.current_kind}
            onChange={switchKind}
            options={[
              { value: "local", label: "Local (free, on this PC)" },
              { value: "cloud", label: "Cloud (your API key)" },
            ]}
          />
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            You can switch any time. The change applies to the next AI job; anything already running finishes first.
          </p>
        </div>
      )}

      {only && overview.current_kind !== kind ? (
        <Button onClick={() => switchKind(kind)}>Use {kind === "local" ? "local AI" : "cloud AI"}</Button>
      ) : (
        <>
          <Field label="Provider">
            <select
              className={inputClass}
              value={current.id}
              onChange={(event) => void update(() => aiApi.setCurrent(event.target.value))}
            >
              {choices.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                  {p.needs_key && p.key_saved ? " (key saved)" : ""}
                </option>
              ))}
            </select>
          </Field>

          {current.id === "ollama" ? (
            <OllamaPanel model={current.model} onModelChange={setOllamaModel} />
          ) : (
            <ProviderPanel key={current.id} provider={current} onChange={onChange} />
          )}

          <div className="flex items-center gap-3 border-t border-zinc-200 pt-4 dark:border-zinc-800">
            <Button variant="secondary" onClick={runTest} disabled={testing}>
              {testing ? "Testing…" : "Test connection"}
            </Button>
            <span className="text-sm text-zinc-500 dark:text-zinc-400">Using {overview.current_label}</span>
          </div>
          {test && <Notice tone={test.ok ? "success" : "error"}>{test.message}</Notice>}
          {kind === "cloud" && (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Cloud AI sends the text of your saved items to {current.label}. Before any batch, the app tells you
              how many requests it will make and asks you to confirm.
            </p>
          )}
        </>
      )}
      {error && <Notice tone="error">{error}</Notice>}
    </div>
  );
}
