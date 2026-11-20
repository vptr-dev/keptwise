import { useRef, useState } from "react";

import { Button, Notice } from "../../components/ui";
import { errorText } from "../../lib/api";
import { enrichApi } from "./enrichApi";

export default function TikTokAccess({ connected, onChange }: { connected: boolean; onChange: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function changeSession(file?: File) {
    setBusy(true);
    setError(null);
    try {
      if (file) await enrichApi.connectTikTok(file);
      else await enrichApi.disconnectTikTok();
      onChange();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="mt-4 border-t border-zinc-200 pt-3 text-sm dark:border-zinc-700">
      <summary className="cursor-pointer font-medium">
        TikTok access {connected && <span className="ml-1 text-emerald-700 dark:text-emerald-400">· Session loaded</span>}
      </summary>
      <p className="mt-2 text-zinc-600 dark:text-zinc-400">
        If TikTok asks you to sign in, check that you can play the video on{" "}
        <a className="font-medium underline" href="https://www.tiktok.com/login" target="_blank" rel="noreferrer">TikTok</a>.
        You can then load a TikTok-only cookies.txt session from your signed-in browser in Netscape format.
        This file acts like a sign-in, so keep it private. Keptwise uses it for TikTok requests until you disconnect
        or close the app. Then retry the affected saves above.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" disabled={busy} onClick={() => input.current?.click()}>
          {connected ? "Replace TikTok session" : "Load TikTok session file"}
        </Button>
        {connected && (
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => void changeSession()}>
            Disconnect
          </Button>
        )}
        <input
          ref={input}
          aria-label="TikTok session file"
          type="file"
          accept=".txt,text/plain"
          className="hidden"
          onChange={(event) => {
            const file = event.currentTarget.files?.[0];
            event.currentTarget.value = "";
            if (file) void changeSession(file);
          }}
        />
      </div>
      {error && <div className="mt-3"><Notice tone="error">{error}</Notice></div>}
    </details>
  );
}
