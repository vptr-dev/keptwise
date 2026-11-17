import { act, fireEvent, render, screen } from "@testing-library/react";
import { useEffect } from "react";
import { expect, test } from "vitest";

import { useDialog, type Ask } from "./Dialog";

function Host({ onReady }: { onReady: (ask: Ask) => void }) {
  const [ask, dialog] = useDialog();
  useEffect(() => {
    onReady(ask);
  }, [ask, onReady]);
  return <>{dialog}</>;
}

test("typing a new name keeps every letter (the old name is only selected when the box opens)", async () => {
  let ask: Ask | null = null;
  render(<Host onReady={(a) => (ask = a)} />);
  let answer: Promise<string | null> = Promise.resolve(null);
  act(() => {
    answer = ask!.text({ title: "Rename collection", label: "Name", value: "Health" });
  });
  const input = (await screen.findByRole("textbox", { name: "Name" })) as HTMLInputElement;
  expect([input.selectionStart, input.selectionEnd]).toEqual([0, 6]); // the old name, ready to type over

  fireEvent.change(input, { target: { value: "H" } });
  fireEvent.change(input, { target: { value: "He" } });
  expect(input.value).toBe("He");
  expect(input.selectionStart).toBe(2); // the cursor stays at the end; nothing is selected again
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await expect(answer).resolves.toBe("He");
});
