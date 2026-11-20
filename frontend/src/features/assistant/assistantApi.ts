// Talking to the backend about the AI Assistant: saved chats and AI tools.
import { api } from "../../lib/api";
import type { LibraryItem } from "../library/libraryApi";

export type ToolId = "ask" | "find" | "summary" | "plan" | "shopping" | "compare" | "takeaways";
// "items": saves the user picked (right-click picked saves -> Ask the AI Assistant).
export type Target = { type: "all" | "collection" | "tag" | "plan" | "items"; id?: number; name?: string; ids?: number[] };

export type ChatSource = { number: number; item_id: number; item: LibraryItem };
// What the AI did in the app for an answer, or is waiting to do (big steps wait for "Do it").
export type PendingAction = { method: string; path: string; body?: Record<string, unknown>; why?: string };
export type ChatActions = { state: "waiting" | "done" | "cancelled"; pending: PendingAction[]; changed: string[] };
export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  found: boolean;
  sources: ChatSource[];
  actions?: ChatActions | null;
  created_at: string;
};
export type ChatSummary = {
  id: number;
  title: string;
  tool: ToolId;
  target: Target | null;
  created_at: string;
  updated_at: string;
  messages: number;
  preview: string;
};
export type Chat = Omit<ChatSummary, "messages" | "preview"> & { target_name: string; messages: ChatMessage[] };

export const assistantApi = {
  chats: () => api.get<{ chats: ChatSummary[] }>("/api/assistant/chats"),
  chat: (id: number) => api.get<Chat>(`/api/assistant/chats/${id}`),
  create: (tool: ToolId = "ask", target: Target | null = null) =>
    api.post<Chat>("/api/assistant/chats", { tool, target }),
  rename: (id: number, title: string) => api.patch<Chat>(`/api/assistant/chats/${id}`, { title }),
  remove: (id: number) => api.del<{ chats: ChatSummary[] }>(`/api/assistant/chats/${id}`),
  send: (id: number, content: string) => api.post<Chat>(`/api/assistant/chats/${id}/messages`, { content }),
  confirm: (id: number, messageId: number, go: boolean) =>
    api.post<Chat>(`/api/assistant/chats/${id}/messages/${messageId}/confirm`, { go }),
};

export type ToolInfo = {
  id: ToolId;
  label: string;
  blurb: string;
  needsGroup: boolean; // works on a collection, tag or plan
  prompt: (name: string) => string;
};

export const TOOLS: ToolInfo[] = [
  {
    id: "ask",
    label: "Ask anything",
    blurb: "Any question, answered only from what you saved.",
    needsGroup: false,
    prompt: () => "",
  },
  {
    id: "find",
    label: "Find saves",
    blurb: "Search for a topic, title or creator and get the matching videos.",
    needsGroup: false,
    prompt: () => "",
  },
  {
    id: "summary",
    label: "Summarise",
    blurb: "What's in a collection, tag or plan, grouped, with the best bits first.",
    needsGroup: true,
    prompt: (name) => `Summarise what's in ${name}.`,
  },
  {
    id: "plan",
    label: "Make a plan",
    blurb: "Turn a group of saves into steps to follow, then save it as a Plan.",
    needsGroup: true,
    prompt: (name) => `Turn ${name} into a plan I can follow.`,
  },
  {
    id: "shopping",
    label: "Shopping or packing list",
    blurb: "One combined list of ingredients, products or things to bring.",
    needsGroup: true,
    prompt: (name) => `Make one shopping list for ${name}.`,
  },
  {
    id: "compare",
    label: "Help me choose",
    blurb: "Compare saves on time, cost and effort, and pick the best one.",
    needsGroup: true,
    prompt: (name) => `Help me choose from ${name}.`,
  },
  {
    id: "takeaways",
    label: "Key takeaways",
    blurb: "The tips, facts and lessons worth remembering, most useful first.",
    needsGroup: true,
    prompt: (name) => `What are the key takeaways from ${name}?`,
  },
];

export const toolInfo = (id: ToolId): ToolInfo => TOOLS.find((t) => t.id === id) ?? TOOLS[0];
