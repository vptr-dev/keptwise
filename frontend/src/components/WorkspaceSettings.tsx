import { useEffect, useState } from "react";
import { Button, Card, Notice, inputClass } from "./ui";

type Spaces = { current: string; items: { id: string; name: string }[] };
type Bridge = { workspaces(): Promise<Spaces>; create_workspace(name: string): Promise<Spaces>; open_workspace(id: string): Promise<void> };
const bridge = () => (window as Window & { pywebview?: { api?: Bridge } }).pywebview?.api;

function useSpaces() {
  const [spaces, setSpaces] = useState<Spaces>();
  const [error, setError] = useState("");
  useEffect(() => {
    let mounted = true;
    const refresh = () => bridge()?.workspaces?.().then(result => { if (mounted) setSpaces(result); })
      .catch(e => { if (mounted) setError(String(e)); });
    refresh();
    window.addEventListener("pywebviewready", refresh);
    return () => { mounted = false; window.removeEventListener("pywebviewready", refresh); };
  }, []);
  return { spaces, setSpaces, error, setError };
}

export function WorkspaceLink({ compact }: { compact: boolean }) {
  const { spaces } = useSpaces();
  const current = spaces?.items.find(s => s.id === spaces.current);
  if (!current) return null;
  return <a href="#/settings?section=workspaces" title={"Workspace: " + current.name + " · Switch workspace"}
    aria-label={"Current workspace: " + current.name + ". Switch workspace"} className="mx-3 mb-2 block truncate rounded-md px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-500/10">
    {compact ? current.name.charAt(0).toUpperCase() : current.name + " workspace"}
  </a>;
}

export default function WorkspaceSettings() {
  const { spaces, setSpaces, error, setError } = useSpaces();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  async function run(operation: () => Promise<void>) {
    setBusy(true); setError("");
    try { await operation(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  return <Card><h2 className="text-lg font-medium">Workspaces</h2>
    <p className="mb-3 text-sm text-zinc-500">Each workspace has its own saves, chats, settings and API keys. Switching reopens Keptwise.</p>
    {spaces ? <>
      {spaces.items.map(space => <div key={space.id} className="flex items-center justify-between gap-3 border-b border-zinc-500/20 py-2">
        <span>{space.name}</span>{space.id === spaces.current ? <span className="text-xs">Current workspace</span> :
        <Button size="sm" disabled={busy} onClick={() => run(() => bridge()!.open_workspace(space.id))}>Open {space.name}</Button>}
      </div>)}
      <form className="mt-3 flex gap-2" onSubmit={e => { e.preventDefault(); void run(async () => {
        setSpaces(await bridge()!.create_workspace(name.trim())); setName("");
      }); }}>
        <input className={inputClass} aria-label="New workspace name" placeholder="New workspace name" value={name}
          maxLength={60} onChange={e => setName(e.target.value)} />
        <Button type="submit" disabled={busy || !name.trim()}>Create workspace</Button>
      </form></> : <p className="text-sm">Open the desktop app to manage workspaces.</p>}
    {error && <Notice tone="error">{error}</Notice>}
  </Card>;
}
