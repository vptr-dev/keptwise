// Runs before every test file.
import "@testing-library/jest-dom/vitest"; // adds checks like toBeInTheDocument()
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup(); // remove whatever the test put on the page
  vi.unstubAllGlobals(); // undo fake fetch() etc.
});
