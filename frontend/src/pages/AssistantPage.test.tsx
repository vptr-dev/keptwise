// Tests for the AI Assistant: saved chats, the AI tools and their answers.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";

import { fakeBackend, httpError } from "../test/fakeBackend";
import { libraryItem } from "../test/libraryItem";
import AssistantPage from "./AssistantPage";

const chat = (overrides: Record<string, unknown> = {}) => ({
  id: 5, title: "New chat", tool: "ask", target: null, target_name: "all my saves", created_at: "", updated_at: "",
  messages: [], ...overrides,
});
const answer = (content: string, sources = [{ number: 1, item_id: 1, item: libraryItem() }]) => ({
  id: 2, role: "assistant", content, found: true, sources, created_at: "",
});
const question = (content: string) => ({ id: 1, role: "user", content, found: true, sources: [], created_at: "" });

afterEach(() => {
  window.location.hash = "";
});

test("start a chat, ask, and open a save the answer used", async () => {
  const calls = fakeBackend({
    "GET /api/assistant/chats": { chats: [] },
    "GET /api/collections": { collections: [], counts: {} },
    "GET /api/tags": { tags: [] },
    "GET /api/plans": { plans: [], open: 0, finished: 0 },
    "POST /api/assistant/chats/5/messages": chat({
      title: "pasta?",
      messages: [question("what pasta did I save?"), answer("You saved a tomato pasta [1].")],
    }),
    "POST /api/assistant/chats": chat(),
    "GET /api/items/1": { item: libraryItem(), transcript: "boil the pasta" },
  });
  render(<AssistantPage chatId={null} />);
  expect(await screen.findByRole("heading", { name: "What do you want to know?" })).toBeInTheDocument();
  expect(screen.getByRole("list", { name: "Ideas" }).children).toHaveLength(6); // an even grid
  // With "All my saves", only Ask anything works; the others need a group.
  expect(screen.getByRole("button", { name: /^Summarise/ })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: /^Ask anything/ }));
  await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ tool: "ask", target: null }));

  fireEvent.change(await screen.findByLabelText("Your message"), { target: { value: "what pasta did I save?" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByTestId("answer")).toHaveTextContent("You saved a tomato pasta 1.");
  expect(calls.find((c) => c.url === "/api/assistant/chats/5/messages")?.body).toEqual({ content: "what pasta did I save?" });
  fireEvent.click(screen.getByRole("button", { name: "Open save 1" }));
  expect(await screen.findByTestId("transcript")).toHaveTextContent("boil the pasta");
});

test("a link from a collection starts a tool and sends its first message", async () => {
  window.location.hash = "#/chat?tool=shopping&collection=3";
  const calls = fakeBackend({
    "GET /api/assistant/chats": { chats: [] },
    "POST /api/assistant/chats/6/messages": chat({
      id: 6, tool: "shopping", target_name: "my Food collection", title: "Shopping or packing list: Food collection",
      messages: [question("Make one shopping list for my Food collection."), answer("* **Tomatoes** [1]")],
    }),
    "POST /api/assistant/chats": chat({ id: 6, tool: "shopping", target: { type: "collection", id: 3 }, target_name: "my Food collection" }),
  });
  render(<AssistantPage chatId={null} />);
  const reply = await screen.findByTestId("answer");
  expect(reply.querySelectorAll("li")).toHaveLength(1);
  expect(screen.getByText("Tomatoes", { selector: "strong" })).toBeInTheDocument();
  expect(calls.find((c) => c.method === "POST" && c.url === "/api/assistant/chats")?.body).toEqual({ tool: "shopping", target: { type: "collection", id: 3 } });
  expect(calls.find((c) => c.url === "/api/assistant/chats/6/messages")?.body).toEqual({
    content: "Make one shopping list for my Food collection.",
  });
  expect(screen.getByRole("button", { name: /Save these 1 as a plan/ })).toBeInTheDocument();
});

test("saved chats are listed, opened and deleted", async () => {
  const calls = fakeBackend({
    "GET /api/assistant/chats": { chats: [{ ...chat({ id: 7, title: "Lisbon ideas" }), messages: 2, preview: "Try the tram" }] },
    "GET /api/assistant/chats/7": chat({ id: 7, title: "Lisbon ideas", messages: [question("lisbon?"), answer("Try the tram [1].")] }),
    "DELETE /api/assistant/chats/7": { chats: [] },
  });
  render(<AssistantPage chatId={7} />);
  expect(await screen.findByRole("heading", { name: "Lisbon ideas" })).toBeInTheDocument();
  expect(screen.getByTestId("answer")).toHaveTextContent("Try the tram 1.");
  fireEvent.click(screen.getByRole("button", { name: "Delete chat Lisbon ideas" }));
  await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
  expect(window.location.hash).toBe("#/chat");
});

test("an AI that isn't ready points to the AI settings and keeps what you typed", async () => {
  fakeBackend({
    "GET /api/assistant/chats": { chats: [] },
    "GET /api/assistant/chats/5": chat(),
    "POST /api/assistant/chats/5/messages": httpError(400, { detail: "The model gemma4:12b isn't downloaded yet.", code: "model_missing" }),
  });
  render(<AssistantPage chatId={5} />);
  fireEvent.change(await screen.findByLabelText("Your message"), { target: { value: "pasta?" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText(/isn't downloaded yet/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Open AI settings" })).toHaveAttribute("href", "#/settings?section=ai");
  expect(screen.getByLabelText("Your message")).toHaveValue("pasta?");
});

test("a Make a plan answer can be saved as a real plan", async () => {
  const calls = fakeBackend({
    "GET /api/assistant/chats": { chats: [] },
    "GET /api/assistant/chats/8": chat({
      id: 8, tool: "plan", title: "Make a plan: Food collection",
      messages: [question("plan it"), answer("1. Buy tomatoes [1]")],
    }),
    "POST /api/plans": { id: 12, name: "Food", items: [] },
  });
  render(<AssistantPage chatId={8} />);
  fireEvent.click(await screen.findByRole("button", { name: /Save these 1 as a plan/ }));
  await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/api/plans")?.body).toMatchObject({ name: "Food", item_ids: [1] }));
  fireEvent.click(await screen.findByRole("button", { name: "Open the plan" }));
  expect(window.location.hash).toBe("#/plans/12");
});

test("the bar at the bottom starts a chat with whatever you type", async () => {
  const calls = fakeBackend({
    "GET /api/assistant/chats": { chats: [] },
    "GET /api/collections": { collections: [], counts: {} },
    "GET /api/tags": { tags: [] },
    "GET /api/plans": { plans: [], open: 0, finished: 0 },
    "POST /api/assistant/chats/5/messages": chat({ title: "gym ideas", messages: [question("any gym ideas?"), answer("Try squats [1].")] }),
    "POST /api/assistant/chats": chat(),
  });
  render(<AssistantPage chatId={null} />);
  expect(await screen.findByText(/This is your/)).toHaveTextContent("AI Assistant");
  fireEvent.change(screen.getByLabelText("Ask anything"), { target: { value: "any gym ideas?" } });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/api/assistant/chats")?.body).toEqual({ tool: "ask", target: null }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/assistant/chats/5/messages")?.body).toEqual({ content: "any gym ideas?" }));
  expect(await screen.findByTestId("answer")).toHaveTextContent("Try squats 1.");
});

test("picked saves are brought into a chat, with ideas for what to ask", async () => {
  window.location.hash = "#/chat?items=4,9";
  const picked = chat({ id: 8, title: "About: 2 saves I picked", target: { type: "items", ids: [4, 9] }, target_name: "the 2 saves I picked" });
  const calls = fakeBackend({
    "GET /api/assistant/chats": { chats: [] },
    "POST /api/assistant/chats/8/messages": { ...picked, messages: [question("Summarise these."), answer("Two recipes [1].")] },
    "POST /api/assistant/chats": picked,
  });
  render(<AssistantPage chatId={null} />);
  await waitFor(() =>
    expect(calls.find((c) => c.method === "POST" && c.url === "/api/assistant/chats")?.body).toEqual({ tool: "ask", target: { type: "items", ids: [4, 9] } }),
  );
  expect(await screen.findByText(/The 2 saves you picked are/)).toBeInTheDocument();
  expect(calls.some((c) => c.url === "/api/assistant/chats/8/messages")).toBe(false); // nothing is sent until you ask
  fireEvent.click(screen.getByRole("button", { name: "Summarise these." }));
  await waitFor(() => expect(calls.find((c) => c.url === "/api/assistant/chats/8/messages")?.body).toEqual({ content: "Summarise these." }));
});
