// Ollama setup: is it running, which models are downloaded, and a
// Download button that runs inside the app with a progress bar.
import { useCallback, useEffect, useState } from "react";

import ProgressBar from "../../components/ProgressBar";
import { Badge, Button, Notice, formatBytes, inputClass } from "../../components/ui";
import { errorCode, errorText } from "../../lib/api";
import { isActive, jobActions, useJobFinished, useJobs, type Job } from "../../lib/jobs";
import { aiApi, type OllamaStatus } from "./aiApi";

/** The newest download job for each model name. */
function latestDownloads(jobs: Job[]): Record<string, Job> {
  const byModel: Record<string, Job> = {};
  for (const job of jobs) {
    const name = String(job.params.model ?? "");
    // jobs are newest first, so the first one seen for a model wins
    if (job.kind === "ollama_pull" && !(name in byModel)) byModel[name] = job;
  }
  return byModel;
}

export default function OllamaPanel({
  model,
  onModelChange,
}: {
  model: string;
  onModelChange: (model: string) => void;
}) {
  const [status, setStatus] = useState<OllamaStatus | null>(null);
  const [checking, setChecking] = useState(false);
  // All jobs, kept live; includes downloads started before this page opened.
  const downloads = latestDownloads(useJobs());
  const [customName, setCustomName] = useState("");
  const [error, setError] = useState<string | null>(null);
  // "no_space": the download can't fit, so the manual command won't help either.
  const [errorKind, setErrorKind] = useState<string | null>(null);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      setStatus(await aiApi.ollama());
    } catch (err) {
      setError(errorText(err));
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  // When a download finishes: refresh the model list and use the new model.
  useJobFinished(["ollama_pull"], (job) => {
    if (job.status !== "done") return;
    void check();
    onModelChange(String(job.params.model ?? ""));
  });

  const download = async (name: string) => {
    setError(null);
    setErrorKind(null);
    try {
      await aiApi.pull(name); // its progress arrives through useJobs()
    } catch (err) {
      setError(errorText(err));
      setErrorKind(errorCode(err));
    }
  };

  if (!status) return <p className="text-sm text-zinc-500">Checking Ollama…</p>;

  if (!status.running) {
    return (
      <div className="space-y-4">
        <Notice tone="warning">
          <p className="font-medium">Ollama isn't running on this PC.</p>
          <ol className="mt-2 list-decimal space-y-1 pl-5">
            <li>
              Download Ollama for Windows from{" "}
              <a className="font-medium underline" href={status.download_page} target="_blank" rel="noreferrer">
                ollama.com/download
              </a>{" "}
              and run the installer.
            </li>
            <li>Open Ollama from the Start menu (it sits in the system tray).</li>
            <li>Come back here and press Check again.</li>
          </ol>
        </Notice>
        <Button variant="secondary" onClick={check} disabled={checking}>
          {checking ? "Checking…" : "Check again"}
        </Button>
      </div>
    );
  }

  const installedOthers = status.installed.filter(
    (name) => !status.recommended.some((rec) => rec.name === name),
  );
  // A failed download only matters while that model is still missing.
  const failedDownload = Object.entries(downloads).find(
    ([name, job]) => job.status === "failed" && !status.installed.includes(name),
  )?.[1];

  return (
    <div className="space-y-4">
      <p className="text-sm text-zinc-600 dark:text-zinc-400">
        Ollama {status.version} is running. Free space for models: {formatBytes(status.free_bytes)}.
      </p>

      <ul className="space-y-3">
        {status.recommended.map((rec) => (
          <ModelRow
            key={rec.name}
            name={rec.name}
            title={rec.label}
            note={`${rec.note} About ${rec.size_gb} GB to download.`}
            installed={rec.installed}
            tooBig={status.free_bytes !== null && status.free_bytes < rec.size_gb * 1e9 * 1.1}
            selected={model === rec.name}
            job={downloads[rec.name]}
            onSelect={() => onModelChange(rec.name)}
            onDownload={() => download(rec.name)}
          />
        ))}
        {installedOthers.map((name) => (
          <ModelRow
            key={name}
            name={name}
            title={name}
            note="Already on this PC."
            installed
            selected={model === name}
            onSelect={() => onModelChange(name)}
            onDownload={() => undefined}
          />
        ))}
      </ul>

      <details className="text-sm">
        <summary className="cursor-pointer text-zinc-600 dark:text-zinc-400">Download a different model</summary>
        <div className="mt-2 flex gap-2">
          <input
            className={inputClass}
            placeholder="e.g. qwen3.5:9b"
            value={customName}
            onChange={(event) => setCustomName(event.target.value)}
            aria-label="Model name"
          />
          <Button variant="secondary" disabled={!customName.trim()} onClick={() => download(customName.trim())}>
            Download
          </Button>
        </div>
      </details>

      {errorKind === "no_space" ? (
        <Notice tone="error">{error}</Notice>
      ) : (
        (error || failedDownload) && (
          <Fallback
            model={String(failedDownload?.params.model ?? model ?? status.default_model)}
            message={error ?? failedDownload?.error ?? ""}
            onCheck={check}
          />
        )
      )}
    </div>
  );
}

function ModelRow(props: {
  name: string;
  title: string;
  note: string;
  installed: boolean;
  tooBig?: boolean; // not enough free disk space to download it
  selected: boolean;
  job?: Job;
  onSelect: () => void;
  onDownload: () => void;
}) {
  const { job } = props;
  const downloading = job && isActive(job);
  return (
    <li
      className={`rounded-xl border p-4 ${
        props.selected ? "border-indigo-500 bg-indigo-50/50 dark:bg-indigo-950/30" : "border-zinc-200 dark:border-zinc-800"
      }`}
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="flex items-center gap-2 font-medium">
            {props.title}
            {props.installed ? <Badge tone="green">Downloaded</Badge> : <Badge>Not downloaded</Badge>}
            {props.selected && <Badge tone="indigo">{props.installed ? "In use" : "Chosen"}</Badge>}
          </p>
          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
            <code>{props.name}</code> · {props.note}
          </p>
          {props.tooBig && !props.installed && (
            <p className="mt-1 text-xs font-medium text-red-600 dark:text-red-400">
              Not enough free disk space for this one. Free up some space, then open Settings again.
            </p>
          )}
        </div>
        <div className="shrink-0">
          {props.installed ? (
            <Button size="sm" variant={props.selected ? "secondary" : "primary"} disabled={props.selected} onClick={props.onSelect}>
              {props.selected ? "Selected" : "Use this"}
            </Button>
          ) : downloading ? (
            <Button size="sm" variant="ghost" onClick={() => jobActions.cancel(job.id)}>
              Cancel
            </Button>
          ) : (
            <Button size="sm" onClick={props.onDownload} disabled={props.tooBig}>
              {job?.status === "cancelled" || job?.status === "interrupted" ? "Resume download" : "Download"}
            </Button>
          )}
        </div>
      </div>
      {downloading && (
        <div className="mt-3 space-y-1">
          <ProgressBar done={job.progress} total={job.total} label={`Downloading ${props.name}`} />
          <p className="text-xs text-zinc-500">{job.message}</p>
        </div>
      )}
    </li>
  );
}

/** Shown when the in-app download can't work: the manual command instead. */
function Fallback({ model, message, onCheck }: { model: string; message: string; onCheck: () => void }) {
  const command = `ollama pull ${model}`;
  const [copied, setCopied] = useState(false);
  return (
    <Notice tone="error">
      <p>{message}</p>
      <p className="mt-2">You can also download it yourself: open PowerShell and run</p>
      <div className="mt-2 flex items-center gap-2">
        <code className="flex-1 rounded-lg bg-white/70 px-3 py-2 font-mono text-zinc-900 dark:bg-black/40 dark:text-zinc-100">
          {command}
        </code>
        <Button
          size="sm"
          variant="secondary"
          onClick={async () => {
            await navigator.clipboard?.writeText(command);
            setCopied(true);
          }}
        >
          {copied ? "Copied" : "Copy"}
        </Button>
        <Button size="sm" variant="secondary" onClick={onCheck}>
          Check again
        </Button>
      </div>
    </Notice>
  );
}
