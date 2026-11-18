import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import Toasts from "../../components/Toasts";
import { fakeBackend } from "../../test/fakeBackend";
import UndoButtons, { onUndo } from "./UndoButtons";

test("Undo takes back the last change, then Redo is offered", async () => {
  let state: object = { undo: { id: 4, label: "Delete collection" }, redo: null };
  const calls = fakeBackend({
    "GET /api/undo": () => state,
    "POST /api/undo": () => {
      state = { undo: null, redo: { id: 4, label: "Delete collection" } };
      return { done: "Delete collection", ...state };
    },
  });
  const reloaded = vi.fn();
  const stop = onUndo(reloaded);
  render(
    <>
      <UndoButtons />
      <Toasts />
    </>,
  );
  const undo = await screen.findByRole("button", { name: "Undo: Delete collection" });
  expect(screen.getByRole("button", { name: "Nothing to redo" })).toBeDisabled();
  fireEvent.click(undo);
  expect(await screen.findByText("Undone: Delete collection")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Redo: Delete collection" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Nothing to undo" })).toBeDisabled();
  expect(calls.some((c) => c.method === "POST" && c.url === "/api/undo")).toBe(true);
  expect(reloaded).toHaveBeenCalled(); // the page on screen loads again
  stop();
});
