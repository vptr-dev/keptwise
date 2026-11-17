// Settings for one provider that isn't Ollama: API key (cloud), address
// (LM Studio), and the model to use.
import { useEffect, useState } from "react";

import { Button, Field, Notice, inputClass } from "../../components/ui";
import { errorText } from "../../lib/api";
import { aiApi, type AiOverview, type ProviderView } from "./aiApi";

export default function ProviderPanel({
  provider,
  onChange,
}: {
  provider: ProviderView;
  onChange: (overview: AiOverview) => void;
}) {
  const [key, setKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [message, setMessage] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const canList = !provider.needs_key || provider.key_saved;

  useEffect(() => {
    setBaseUrl(provider.base_url);
    setModels([]);
    if (!canList) return;
    let active = true;
    aiApi
      .models(provider.id)
      .then((result) => {
        if (!active) return;
        setModels(result.models);
        if (result.model !== provider.model) void aiApi.overview().then(onChange);
      })
      .catch((err) => active && setMessage({ tone: "error", text: errorText(err) }));
    return () => {
      active = false;
    };
  }, [provider.id, provider.key_saved, provider.base_url]);

  const run = async (action: () => Promise<AiOverview | void>, success?: string) => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await action();
      if (result) onChange(result);
      if (success) setMessage({ tone: "success", text: success });
    } catch (err) {
      setMessage({ tone: "error", text: errorText(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {provider.needs_key && (
        <Field
          label={`${provider.label} API key`}
          hint={
            <>
              Saved in Windows Credential Manager, never in a file.{" "}
              {provider.key_url && (
                <a className="text-indigo-600 underline dark:text-indigo-400" href={provider.key_url} target="_blank" rel="noreferrer">
                  Get a key
                </a>
              )}
            </>
          }
        >
          <div className="flex gap-2">
            <input
              type="password"
              autoComplete="off"
              className={inputClass}
              placeholder={provider.key_saved ? `Saved (${provider.key_hint})` : "Paste your API key"}
              value={key}
              onChange={(event) => setKey(event.target.value)}
            />
            <Button
              disabled={!key.trim() || busy}
              onClick={() =>
                run(async () => {
                  const result = await aiApi.saveKey(provider.id, key);
                  setKey("");
                  return result;
                }, "Key saved.")
              }
            >
              Save key
            </Button>
            {provider.key_saved && (
              <Button variant="secondary" disabled={busy} onClick={() => run(() => aiApi.removeKey(provider.id), "Key removed.")}>
                Remove key
              </Button>
            )}
          </div>
        </Field>
      )}

      {provider.kind === "local" && (
        <Field label="Address" hint={`Default: ${provider.default_base_url}`}>
          <div className="flex gap-2">
            <input className={inputClass} value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} />
            <Button variant="secondary" disabled={busy || baseUrl === provider.base_url} onClick={() => run(() => aiApi.setBaseUrl(provider.id, baseUrl))}>
              Save
            </Button>
          </div>
        </Field>
      )}

      {canList && (
        <Field label="Model">
          {models.length > 0 ? (
            <select
              className={inputClass}
              value={provider.model}
              onChange={(event) => run(() => aiApi.setModel(provider.id, event.target.value))}
            >
              {!models.includes(provider.model) && <option value={provider.model}>{provider.model || "Pick a model"}</option>}
              {models.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          ) : (
            <input
              className={inputClass}
              defaultValue={provider.model}
              placeholder="Model name"
              onBlur={(event) => event.target.value !== provider.model && run(() => aiApi.setModel(provider.id, event.target.value))}
            />
          )}
        </Field>
      )}

      {message && <Notice tone={message.tone}>{message.text}</Notice>}
    </div>
  );
}
