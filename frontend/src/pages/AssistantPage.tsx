// AI Assistant (#/chat, #/chat/12): saved chats on the left, the open chat on
// the right. Type anything in the bar at the bottom to start a chat, or pick
// an idea that works on a collection, tag or plan: Summarise, Make a plan,
// Shopping or packing list, Help me choose, Key takeaways. Every answer comes
// only from your saves and shows the ones it used. A "Make a plan" answer can
// be saved as a real Plan.
// Other screens link here with ?tool=summary&collection=3 (or tag=, plan=),
// with ?items=4,9,12 to talk about picked saves, and the Search screen with
// ?q=... to ask straight away.
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { icons } from "../components/icons";
import { Button, Notice, inputClass } from "../components/ui";
import AnswerText from "../features/assistant/AnswerText";
import { TOOLS, assistantApi, toolInfo, type Chat, type ChatActions,
  type ChatMessage, type ChatSummary, type Target, type ToolId } from "../features/assistant/assistantApi";
import { organizeApi, type Tag } from "../features/organize/organizeApi";
import { plansApi, type PlanSummary } from "../features/plans/plansApi";
import ItemPanel from "../features/search/ItemPanel";
import ResultCard from "../features/search/ResultCard";
import { sortingApi, type Collection } from "../features/sorting/sortingApi";
import { errorCode, errorText } from "../lib/api";
import { navigate, useRoute } from "../lib/router";

const SETTINGS_CODES = ["missing_key", "missing_model", "model_missing", "unreachable"];
const EXAMPLES = ["Find my videos about pasta", "Which places did I save in London?", "Summarise my skincare tips"];

const TOOL_ICONS: Record<ToolId, ReactNode> = {
  ask: icons.chat,
  find: icons.search,
  summary: icons.list,
  plan: icons.plans,
  shopping: icons.cart,
  compare: icons.scale,
  takeaways: icons.bulb,
};

// What to offer when picked saves were brought into a chat.
const PICKED_IDEAS = [
  "Summarise these.",
  "What are the key takeaways?",
  "Turn these into a plan I can follow.",
  "Help me choose between them.",
  "Make one shopping or packing list from them.",
  "What do they have in common?",
];

export default function AssistantPage({ chatId }: { chatId: number | null }) {
  const route = useRoute();
  const [chats, setChats] = useState<ChatSummary[] | null>(null);
  const [chat, setChat] = useState<Chat | null>(null);
  const [error, setError] = useState<{ text: string; code: string | null } | null>(null);
  const [text, setText] = useState("");
  const [pending, setPending] = useState<Set<number>>(() => new Set());
  const [creating, setCreating] = useState(false);
  const requests = useRef(new Set<number>());
  const starting = useRef(false);
  const visibleChat = useRef(chatId);
  const busy = chat ? pending.has(chat.id) : creating;
  const [openId, setOpenId] = useState<number | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [title, setTitle] = useState("");
  const bottom = useRef<HTMLDivElement>(null);
  const handledLink = useRef<string | null>(null);

  const loadChats = useCallback(() => {
    assistantApi.chats().then((c) => setChats(c.chats)).catch(() => setChats([]));
  }, []);
  useEffect(loadChats, [loadChats]);

  useEffect(() => {
    visibleChat.current = chatId;
    setError(null);
    setRenaming(false);
    setOpenId(null);
    setText("");
    setChat((current) => current?.id === chatId ? current : null);
    if (chatId === null || !Number.isInteger(chatId)) {
      setChat(null);
      return;
    }
    let active = true;
    assistantApi
      .chat(chatId)
      .then((loaded) => {
        if (active) setChat((current) =>
          current?.id === loaded.id && current.messages.length > loaded.messages.length ? current : loaded);
      })
      .catch((e) => {
        if (!active) return;
        setChat(null);
        setError({ text: errorText(e), code: null });
      });
    return () => { active = false; };
  }, [chatId]);

  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [chat?.messages.length, busy]);

  const begin = useCallback((id: number) => {
    if (requests.current.has(id)) return false;
    requests.current.add(id);
    setPending(new Set(requests.current));
    return true;
  }, []);

  const finish = useCallback((id: number) => {
    requests.current.delete(id);
    setPending(new Set(requests.current));
  }, []);

  const send = useCallback(
    async (target: Chat, content: string) => {
      content = content.trim();
      if (!content || !begin(target.id)) return;
      setError(null);
      const optimistic: ChatMessage = { id: -1, role: "user", content, found: true, sources: [], created_at: "" };
      setChat({ ...target, messages: [...target.messages, optimistic] });
      setText("");
      try {
        const reply = await assistantApi.send(target.id, content);
        if (visibleChat.current === target.id) setChat(reply);
        loadChats();
      } catch (e) {
        if (visibleChat.current === target.id) {
          setChat(target);
          setText(content);
          setError({ text: errorText(e), code: errorCode(e) });
        }
      } finally {
        finish(target.id);
      }
    },
    [begin, finish, loadChats],
  );

  const confirm = useCallback(async (target: Chat, messageId: number, go: boolean) => {
    if (!begin(target.id)) return;
    setError(null);
    try {
      const reply = await assistantApi.confirm(target.id, messageId, go);
      if (visibleChat.current === target.id) setChat(reply);
      loadChats();
    } catch (e) {
      if (visibleChat.current === target.id) setError({ text: errorText(e), code: errorCode(e) });
    } finally {
      finish(target.id);
    }
  }, [begin, finish, loadChats]);

  const start = useCallback(
    async (tool: ToolId, target: Target | null, firstMessage?: string) => {
      if (starting.current) return;
      starting.current = true;
      setCreating(true);
      const from = window.location.hash;
      setError(null);
      try {
        const made = await assistantApi.create(tool, target);
        loadChats();
        if (window.location.hash !== from) return;
        visibleChat.current = made.id;
        navigate(`/chat/${made.id}`);
        setChat(made);
        const prompt = firstMessage ?? (tool !== "ask" ? toolInfo(tool).prompt(made.target_name) : "");
        if (prompt) void send(made, prompt);
      } catch (e) {
        if (window.location.hash === from) setError({ text: errorText(e), code: errorCode(e) });
      } finally {
        starting.current = false;
        setCreating(false);
      }
    },
    [loadChats, send],
  );

  // Links from other screens: ?q=..., or ?tool=...&collection= / tag= / plan=
  useEffect(() => {
    if (chatId !== null || !route.query.size) {
      handledLink.current = null;
      return;
    }
    const link = route.query.toString();
    if (handledLink.current === link) return;
    const q = route.query.get("q");
    const tool = route.query.get("tool") as ToolId | null;
    const picked = (route.query.get("items") ?? "").split(",").map(Number).filter((n) => Number.isInteger(n) && n > 0);
    if (!q && !tool && picked.length === 0) return;
    handledLink.current = link;
    const collection = route.query.get("collection");
    const tag = route.query.get("tag");
    const plan = route.query.get("plan");
    const target: Target | null = picked.length
      ? { type: "items", ids: picked }
      : collection
      ? { type: "collection", id: Number(collection) }
      : tag
        ? { type: "tag", name: tag }
        : plan
          ? { type: "plan", id: Number(plan) }
          : null;
    void start(tool && TOOLS.some((t) => t.id === tool) ? tool : "ask", target, q ?? undefined);
  }, [route.query, chatId, start]);

  async function remove(id: number) {
    try {
      const left = await assistantApi.remove(id);
      setChats(left.chats);
      if (visibleChat.current === id) navigate("/chat");
    } catch (e) {
      setError({ text: errorText(e), code: errorCode(e) });
    }
  }

  async function rename(event: FormEvent) {
    event.preventDefault();
    if (!chat || !title.trim()) return;
    setRenaming(false);
    try {
      const renamed = await assistantApi.rename(chat.id, title.trim());
      if (visibleChat.current === renamed.id) setChat(renamed);
      loadChats();
    } catch (e) {
      if (visibleChat.current === chat.id) setError({ text: errorText(e), code: errorCode(e) });
    }
  }

  return (
    <div className="flex h-full min-h-0">
      <aside className="flex w-36 shrink-0 flex-col bg-zinc-500/[.05] sm:w-44 xl:w-56" aria-label="Chats">
        <div className="p-3">
          <Button variant="secondary" className="w-full" onClick={() => navigate("/chat")}>
            <span className="h-4 w-4">{icons.plus}</span>
            New chat
          </Button>
        </div>
        <ul className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {chats?.length === 0 && <li className="px-3 py-6 text-center text-xs text-zinc-500">Your chats are kept here.</li>}
          {chats?.map((c) => (
            <li key={c.id} className="group relative">
              <a
                href={`#/chat/${c.id}`}
                aria-current={chat?.id === c.id ? "page" : undefined}
                className={`flex items-start gap-2 rounded-lg px-2.5 py-2 pr-8 text-sm ${
                  chat?.id === c.id
                    ? "bg-indigo-50 text-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-200"
                    : "text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
                }`}
              >
                <span className="mt-0.5 h-4 w-4 shrink-0 text-zinc-400">{TOOL_ICONS[c.tool] ?? icons.chat}</span>
                <span className="min-w-0">
                  <span className="block truncate font-medium">{c.title}</span>
                  <span className="block truncate text-xs text-zinc-500">{c.preview || toolInfo(c.tool).label}</span>
                </span>
              </a>
              <button
                type="button"
                onClick={() => void remove(c.id)}
                disabled={pending.has(c.id)}
                aria-label={`Delete chat ${c.title}`}
                title="Delete chat"
                className="absolute right-1.5 top-2 hidden h-6 w-6 items-center justify-center rounded-md p-1 text-zinc-400 hover:bg-zinc-200 hover:text-red-600 group-hover:flex group-focus-within:flex disabled:opacity-50 dark:hover:bg-zinc-700"
              >
                {icons.trash}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {chat ? (
          <>
            <header className="flex flex-wrap items-center gap-3 px-4 py-3.5 xl:px-6">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-50 p-1.5 text-indigo-600 dark:bg-indigo-950/60 dark:text-indigo-300">{TOOL_ICONS[chat.tool]}</span>
              {renaming ? (
                <form onSubmit={rename} className="flex flex-1 gap-2">
                  <input className={`${inputClass} py-1`} aria-label="Chat name" autoFocus maxLength={80} value={title} onChange={(e) => setTitle(e.target.value)} />
                  <Button size="sm" type="submit">Save</Button>
                  <Button size="sm" variant="ghost" onClick={() => setRenaming(false)}>Cancel</Button>
                </form>
              ) : (
                <>
                  <div className="min-w-0 flex-1">
                    <h1 className="truncate font-semibold">{chat.title}</h1>
                    <p className="kw-tip truncate text-xs text-zinc-500">
                      {toolInfo(chat.tool).label} · {chat.tool === "ask" && !chat.target ? "answers from all your saves" : `working on ${chat.target_name}`}
                    </p>
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => { setTitle(chat.title); setRenaming(true); }}>
                    Rename
                  </Button>
                </>
              )}
            </header>
            <div className="flex-1 overflow-y-auto px-6 py-6">
              <div className="mx-auto max-w-3xl space-y-6">
                {chat.messages.length === 0 && !busy && (
                  <Starter chat={chat} onAsk={(q) => void send(chat, q)} />
                )}
                {chat.messages.map((message, index) =>
                  message.role === "user" ? (
                    <div key={`${message.id}-${index}`} className="flex justify-end">
                      <p className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 text-sm text-white">{message.content}</p>
                    </div>
                  ) : (
                    <Answer
                      key={message.id}
                      message={message}
                      tool={chat.tool}
                      chatTitle={chat.title}
                      onOpen={setOpenId}
                      onConfirm={busy ? undefined : (go) => void confirm(chat, message.id, go)}
                    />
                  ),
                )}
                {busy && (
                  <p className="flex items-center gap-2 text-sm text-zinc-500" role="status" aria-label="Waiting for reply">
                    <span className="flex gap-1" aria-hidden="true">
                      {[0, 1, 2].map((dot) => (
                        <span key={dot} className="h-1.5 w-1.5 animate-bounce rounded-full bg-current" style={{ animationDelay: `${dot * 120}ms` }} />
                      ))}
                    </span>
                  </p>
                )}
                {error && (
                  <Notice tone="error" onClose={() => setError(null)}>
                    {error.text}
                    {error.code && SETTINGS_CODES.includes(error.code) && (
                      <>
                        {" "}
                        <a href="#/settings?section=ai" className="font-medium underline">
                          Open AI settings
                        </a>
                      </>
                    )}
                  </Notice>
                )}
                <div ref={bottom} className="scroll-mb-4" />
              </div>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void send(chat, text);
              }}
              className="px-6 pb-5 pt-2"
            >
              <div className="kw-glass mx-auto flex max-w-3xl items-center gap-2 rounded-2xl border p-2 pl-4 focus-within:ring-2 focus-within:ring-indigo-500/40">
                <input
                  className="min-w-0 flex-1 bg-transparent py-2 text-[15px] outline-none placeholder:text-zinc-400"
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder={chat.tool === "ask" ? "Ask about your saves, e.g. “what pasta recipes did I save?”" : "Ask a follow-up, e.g. “only the vegetarian ones”"}
                  aria-label="Your message"
                  disabled={busy}
                  maxLength={4000}
                />
                <Button type="submit" disabled={busy || !text.trim()}>
                  Send
                </Button>
              </div>
            </form>
          </>
        ) : (
          <div className="flex-1 overflow-y-auto px-6 py-10">
            <div className="mx-auto max-w-3xl space-y-8">
              <header className="space-y-5 text-center">
                <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 p-3 text-white shadow-lg shadow-indigo-500/25 dark:bg-indigo-500 dark:text-zinc-950">
                  {icons.sparkle}
                </span>
                <div>
                  <h1 className="text-2xl font-semibold tracking-tight">What can I help with?</h1>
                  <p className="kw-tip mt-1.5 text-sm text-zinc-600 dark:text-zinc-400">
                    Find videos, ask what they said, or pick a collection to work with.
                  </p>
                </div>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (text.trim()) void start("ask", null, text);
                  }}
                  className="kw-glass flex items-center gap-2 rounded-2xl border p-2 pl-4 text-left focus-within:ring-2 focus-within:ring-indigo-500/40"
                >
                  <span className="h-5 w-5 shrink-0 text-zinc-400">{icons.search}</span>
                  <input
                    className="min-w-0 flex-1 bg-transparent py-2 text-[15px] outline-none placeholder:text-zinc-400"
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    placeholder="Find a video or ask about your saves…"
                    aria-label="Ask anything"
                    autoFocus
                    maxLength={4000}
                  />
                  <Button type="submit" disabled={creating || !text.trim()}>
                    Ask
                  </Button>
                </form>
                <div className="flex flex-wrap justify-center gap-2">
                  {EXAMPLES.map((example) => (
                    <button
                      key={example}
                      type="button"
                      onClick={() => void start("ask", null, example)}
                      className="kw-btn rounded-full border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 hover:border-zinc-300 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-400 dark:hover:text-white"
                    >
                      {example}
                    </button>
                  ))}
                </div>
              </header>
              {error && <Notice tone="error" onClose={() => setError(null)}>{error.text}</Notice>}
              <ToolGallery onStart={(tool, target) => void start(tool, target)} />
            </div>
          </div>
        )}
      </div>
      {openId !== null && <ItemPanel itemId={openId} onClose={() => setOpenId(null)} />}
    </div>
  );
}

function Starter({ chat, onAsk }: { chat: Chat; onAsk: (text: string) => void }) {
  const info = toolInfo(chat.tool);
  if (chat.target?.type === "items") {
    const count = chat.target.ids?.length ?? 0;
    return (
      <div className="kw-glass rounded-2xl border p-5">
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          {count === 1 ? "The save you picked is" : `The ${count} saves you picked are`} here. Ask anything about{" "}
          {count === 1 ? "it" : "them"} below, or start with one of these:
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {PICKED_IDEAS.slice(0, count === 1 ? 2 : PICKED_IDEAS.length).map((idea) => (
            <Button key={idea} variant="secondary" size="sm" onClick={() => onAsk(idea)}>
              {idea}
            </Button>
          ))}
        </div>
      </div>
    );
  }
  if (chat.tool === "find") {
    return <p className="text-sm text-zinc-500">Enter a title, creator or topic to search your saves.</p>;
  }
  if (chat.tool === "ask") {
    return (
      <div className="kw-glass rounded-2xl border p-5">
        <p className="text-sm text-zinc-600 dark:text-zinc-300">Try one of these, or type your own question below.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <Button key={example} variant="secondary" size="sm" onClick={() => onAsk(example)}>
              {example}
            </Button>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="kw-glass rounded-2xl border p-5">
      <p className="text-sm text-zinc-600 dark:text-zinc-300">{info.blurb}</p>
      <Button className="mt-3" onClick={() => onAsk(info.prompt(chat.target_name))}>
        {info.label} for {chat.target_name.replace(/^my /, "")}
      </Button>
    </div>
  );
}

function ToolGallery({ onStart }: { onStart: (tool: ToolId, target: Target | null) => void }) {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);
  const [plans, setPlans] = useState<PlanSummary[]>([]);

  useEffect(() => {
    sortingApi.collections().then((o) => setCollections(o.collections)).catch(() => undefined);
    organizeApi.tags().then((t) => setTags(t.tags.filter((tag) => tag.count > 0).slice(0, 60))).catch(() => undefined);
    plansApi.list().then((l) => setPlans(l.plans)).catch(() => undefined);
  }, []);

  function targetOf(value: string | undefined): Target | null {
    if (!value) return null;
    const [type, ref] = value.split(":");
    if (type === "collection" || type === "plan") return { type, id: Number(ref) };
    if (type === "tag") return { type: "tag", name: ref };
    return null; // all my saves
  }

  const [value, setValue] = useState("all");
  const target = targetOf(value);
  const nothing = collections.length === 0 && plans.length === 0 && tags.length === 0;

  return (
    <section className="space-y-4" aria-label="Work on a group of saves">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Work on</h2>
        <select aria-label="What the tools work on" value={value} onChange={(e) => setValue(e.target.value)} className={`${inputClass} !w-auto min-w-56 py-1.5`}>
          <option value="all">All my saves</option>
          {collections.length > 0 && (
            <optgroup label="Collections">
              {collections.map((c) => (
                <option key={c.id} value={`collection:${c.id}`}>
                  {"\u00a0\u00a0".repeat(c.depth)}
                  {c.name} ({c.count})
                </option>
              ))}
            </optgroup>
          )}
          {plans.length > 0 && (
            <optgroup label="Plans">
              {plans.map((p) => (
                <option key={p.id} value={`plan:${p.id}`}>
                  {p.name} ({p.item_count})
                </option>
              ))}
            </optgroup>
          )}
          {tags.length > 0 && (
            <optgroup label="Tags">
              {tags.map((t) => (
                <option key={t.id} value={`tag:${t.name}`}>
                  #{t.name} ({t.count})
                </option>
              ))}
            </optgroup>
          )}
        </select>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Ideas">
        {TOOLS.map((tool) => {
          const blocked = tool.needsGroup && !target;
          return (
            <li key={tool.id} className="flex">
              <button
                type="button"
                disabled={blocked}
                title={blocked ? (nothing ? "Make a collection, tag or plan first" : "Pick a collection, tag or plan above first") : undefined}
                onClick={() => onStart(tool.id, target)}
                className="kw-tile group flex w-full flex-col items-start gap-3 p-4 text-left disabled:cursor-not-allowed disabled:opacity-50"
              >
                <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 p-2 text-indigo-600 transition group-enabled:group-hover:bg-indigo-600 group-enabled:group-hover:text-white dark:bg-indigo-950/60 dark:text-indigo-300 dark:group-enabled:group-hover:bg-indigo-500 dark:group-enabled:group-hover:text-zinc-950">
                  {TOOL_ICONS[tool.id]}
                </span>
                <span>
                  <span className="block font-medium">{tool.label}</span>
                  <span className="mt-0.5 block text-sm text-zinc-500 dark:text-zinc-400">{tool.blurb}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {!target && <p className="text-xs text-zinc-500">Pick a collection, tag or plan above to use the other ideas on it.</p>}
    </section>
  );
}

function Answer({
  message,
  tool,
  chatTitle,
  onOpen,
  onConfirm,
}: {
  message: ChatMessage;
  tool: ToolId;
  chatTitle: string;
  onOpen: (id: number) => void;
  onConfirm?: (go: boolean) => void;
}) {
  const byNumber = new Map(message.sources.map((s) => [s.number, s.item_id]));
  const [saved, setSaved] = useState<number | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function saveAsPlan() {
    setProblem(null);
    try {
      const name = chatTitle.replace(/^Make a plan: /, "").replace(/ collection$/, "") || "My plan";
      const plan = await plansApi.create(name, message.sources.map((s) => s.item_id), message.content.slice(0, 500));
      setSaved(plan.id);
    } catch (e) {
      setProblem(errorText(e));
    }
  }

  return (
    <div className="space-y-3">
      <div
        className="max-w-[90%] space-y-1.5 rounded-2xl rounded-bl-md border border-zinc-200 bg-white px-4 py-3 text-sm leading-relaxed text-zinc-800 shadow-sm dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
        data-testid="answer"
      >
        <AnswerText text={message.content} byNumber={byNumber} onOpen={onOpen} />
      </div>
      {message.actions && (message.actions.state !== "done" || message.actions.changed.length > 0) &&
        <ActionsDone actions={message.actions} onConfirm={onConfirm} />}
      {message.found && message.sources.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          {(tool === "ask" || tool === "find") && (
            <>
              <Button size="sm" variant="ghost"
                onClick={() => navigate(`/chat?items=${message.sources.map((s) => s.item_id).join(",")}`)}>
                Ask about these saves
              </Button>
              {message.sources.length > 1 && (
                <Button size="sm" variant="ghost"
                  onClick={() => navigate(`/chat?tool=compare&items=${message.sources.map((s) => s.item_id).join(",")}`)}>
                  Compare these
                </Button>
              )}
            </>
          )}
          {(tool === "plan" || tool === "shopping" || tool === "compare") &&
            (saved ? (
              <Button size="sm" variant="secondary" onClick={() => navigate(`/plans/${saved}`)}>
                Open the plan
              </Button>
            ) : (
              <Button size="sm" variant={tool === "plan" ? "primary" : "secondary"} onClick={() => void saveAsPlan()}>
                <span className="h-4 w-4">{icons.plans}</span>
                Save these {message.sources.length} as a plan
              </Button>
            ))}
          {problem && <span className="text-xs text-red-600">{problem}</span>}
        </div>
      )}
      {message.sources.length > 0 && (
        <details className="group" open>
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-zinc-500">
            {message.sources.length === 1 ? "1 save" : `${message.sources.length} saves`}
          </summary>
          <div className="mt-2 space-y-2">
            {message.sources.map((source) => (
              <ResultCard key={source.item_id} item={source.item} number={source.number} onOpen={onOpen} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

/** What the AI did in the app, or the big steps it's waiting to do. */
function ActionsDone({ actions, onConfirm }: { actions: ChatActions; onConfirm?: (go: boolean) => void }) {
  if (actions.state === "waiting")
    return (
      <div className="kw-glass max-w-[90%] rounded-2xl border p-4 text-sm" role="group" aria-label="Waiting for your OK">
        <p className="font-medium text-zinc-900 dark:text-zinc-100">This is a big change, so I'll wait for you:</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-zinc-700 dark:text-zinc-300">
          {actions.pending.map((action, index) => (
            <li key={index}>{action.why || `${action.method} ${action.path}`}</li>
          ))}
        </ul>
        <div className="mt-3 flex gap-2">
          <Button size="sm" disabled={!onConfirm} onClick={() => onConfirm?.(true)}>
            Do it
          </Button>
          <Button size="sm" variant="secondary" disabled={!onConfirm} onClick={() => onConfirm?.(false)}>
            Cancel
          </Button>
        </div>
        <p className="kw-tip mt-2 text-xs text-zinc-500 dark:text-zinc-400">You can undo it afterwards with the arrow at the top right.</p>
      </div>
    );
  if (actions.state === "cancelled") return <p className="text-xs text-zinc-500 dark:text-zinc-400">Cancelled. Nothing was changed.</p>;
  if (actions.changed.length === 0) return null;
  return (
    <details className="max-w-[90%] text-xs text-zinc-500 dark:text-zinc-400">
      <summary className="cursor-pointer select-none">
        Changed {actions.changed.length} thing{actions.changed.length === 1 ? "" : "s"} (undo with the arrow at the top right, or ask me)
      </summary>
      <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
        {actions.changed.map((line, index) => (
          <li key={index}>{line}</li>
        ))}
      </ul>
    </details>
  );
}
