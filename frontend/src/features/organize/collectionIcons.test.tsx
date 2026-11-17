// Tests for a collection's icon: ready-made ones and your own picture.
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import FolderIcon from "./FolderIcon";
import { IconPicker, readPicture } from "./collectionIcons";

test("pick a ready-made icon, none, or upload a picture of your own", () => {
  const onPick = vi.fn();
  const onUpload = vi.fn();
  render(<IconPicker value="plane" onPick={onPick} onUpload={onUpload} />);
  expect(screen.getByRole("radio", { name: "Travel" })).toHaveAttribute("aria-checked", "true");
  fireEvent.click(screen.getByRole("radio", { name: "Star" }));
  expect(onPick).toHaveBeenCalledWith("star");
  fireEvent.click(screen.getByRole("radio", { name: "No icon" }));
  expect(onPick).toHaveBeenLastCalledWith(null);

  const file = new File(["x"], "cat.png", { type: "image/png" });
  fireEvent.change(screen.getByLabelText("Choose a picture for this collection"), { target: { files: [file] } });
  expect(onUpload).toHaveBeenCalledWith(file);
});

test("only pictures of a sensible size are read", async () => {
  await expect(readPicture(new File(["x"], "notes.txt", { type: "text/plain" }))).rejects.toThrow(/isn't a picture/);
  const huge = new File([new Uint8Array(2_600_000)], "big.png", { type: "image/png" });
  await expect(readPicture(huge)).rejects.toThrow(/too big/);
  await expect(readPicture(new File(["x"], "cat.png", { type: "image/png" }))).resolves.toMatch(/^data:image\/png;base64,/);
});

test("the folder shows the chosen icon or your own picture", () => {
  const { container, rerender } = render(<FolderIcon icon="star" collectionId={4} />);
  expect(container.querySelector('[data-icon="star"]')).not.toBeNull();
  rerender(<FolderIcon icon="custom:1700" collectionId={4} />);
  expect(container.querySelector('image[data-icon="custom"]')).toHaveAttribute("href", "/api/collections/4/icon?v=1700");
  rerender(<FolderIcon icon={null} collectionId={4} />);
  expect(container.querySelector("[data-icon]")).toBeNull();
});
