import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import { fakeBackend } from "../../test/fakeBackend";
import { RowSelection, SaveControls } from "./SaveControls";

test("hover controls select several videos and archive only that selection", async () => {
  const calls = fakeBackend({ "POST /api/items/bulk": { changed: 2, items: [] } });
  render(<RowSelection><SaveControls id={17} title="Pasta" /><SaveControls id={24} title="Soup" /></RowSelection>);
  fireEvent.click(screen.getByRole("button", {name: "Select Pasta"}));
  fireEvent.click(screen.getByRole("button", {name: "Select Soup"}));
  expect(screen.getByRole("toolbar")).toHaveTextContent("2 selected");
  fireEvent.click(screen.getByRole("button", {name: "Archive selected"}));
  await waitFor(() => expect(screen.queryByRole("toolbar")).toBeNull());
  expect(calls[0].body).toEqual({ action: "delete", item_ids: [17, 24] });
});
