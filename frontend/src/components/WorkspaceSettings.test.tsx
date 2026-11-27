import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import WorkspaceSettings from "./WorkspaceSettings";

test("create a workspace without switching until Open is chosen", async () => {
  const personal = { id: "default", name: "Personal" };
  const open_workspace = vi.fn().mockResolvedValue(undefined);
  const create_workspace = vi.fn().mockResolvedValue({ current: "default", items: [personal, { id: "second", name: "Study" }] });
  Object.defineProperty(window, "pywebview", { configurable: true, value: {api: {
    workspaces: async () => ({current: "default", items: [personal]}), create_workspace, open_workspace,
  }}});
  try {
    render(<WorkspaceSettings />);
    fireEvent.change(await screen.findByLabelText("New workspace name"), {target: {value: "Study"}});
    fireEvent.click(screen.getByRole("button", {name: "Create workspace"}));
    const open = await screen.findByRole("button", {name: "Open Study"});
    expect(create_workspace).toHaveBeenCalledWith("Study");
    expect(open_workspace).not.toHaveBeenCalled();
    fireEvent.click(open);
    await waitFor(() => expect(open_workspace).toHaveBeenCalledWith("second"));
  } finally { Reflect.deleteProperty(window, "pywebview"); }
});
