// Settings section: which speech-to-text model to use, and where it runs.
import { useEffect, useState } from "react";

import { Card, Field, Notice, Segmented, inputClass, formatBytes } from "../../components/ui";
import { errorText } from "../../lib/api";
import { enrichApi, type SpeechSettings as Speech } from "./enrichApi";

export default function SpeechSettings() {
  const [speech, setSpeech] = useState<Speech | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    enrichApi
      .overview()
      .then((overview) => setSpeech(overview.speech))
      .catch((e) => setError(errorText(e)));
  }, []);

  async function save(changes: Partial<Pick<Speech, "model" | "device">>) {
    setError(null);
    try {
      setSpeech(await enrichApi.saveSettings(changes));
    } catch (e) {
      setError(errorText(e));
    }
  }

  const chosen = speech?.models.find((model) => model.id === speech.model);

  return (
    <Card>
      <h2 className="mb-1 text-lg font-medium">Speech to text</h2>
      <p className="kw-tip mb-5 text-sm text-zinc-500 dark:text-zinc-400">
        Writes down what's said in each video, on this PC. Bigger models make fewer mistakes but take longer. The
        model downloads once, the first time it's needed. A change applies to the next batch.
      </p>
      {error && (
        <div className="mb-4">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      {speech ? (
        <div className="space-y-5">
          <Field
            label="Model"
            hint={chosen ? `${chosen.hint} ${chosen.downloaded ? "Downloaded." : `About ${formatBytes(chosen.approx_bytes)} to download.`}` : undefined}
          >
            <select
              className={inputClass}
              value={speech.model}
              aria-label="Speech model"
              onChange={(event) => save({ model: event.target.value })}
            >
              {speech.models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label} · {formatBytes(model.approx_bytes)}
                  {model.downloaded ? " · downloaded" : ""}
                </option>
              ))}
            </select>
          </Field>
          <div className="space-y-1.5">
            <span className="block text-sm font-medium text-zinc-800 dark:text-zinc-200">Run it on</span>
            <Segmented
              label="Run speech to text on"
              value={speech.device}
              options={[
                { value: "auto", label: "Graphics card if possible" },
                { value: "cpu", label: "Processor only" },
              ]}
              onChange={(device) => save({ device })}
            />
            <span className="kw-tip block text-xs text-zinc-500 dark:text-zinc-400">
              An NVIDIA graphics card is about 4 times faster (a 3-minute video in about 5 seconds). On other PCs the
              processor is used, which works fine, just slower.
            </span>
          </div>
        </div>
      ) : (
        !error && <Notice>Loading…</Notice>
      )}
    </Card>
  );
}
