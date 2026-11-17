import { expect, test, vi } from "vitest";

import { ApiError, api, errorCode, errorText } from "./api";

test("backend errors keep their message and code", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status: 400,
      json: async () => ({ detail: "Not enough free disk space", code: "no_space" }),
    })),
  );
  const error = await api.post("/api/ai/ollama/pull", { model: "x" }).catch((err: unknown) => err);
  expect(error).toBeInstanceOf(ApiError);
  expect(errorText(error)).toBe("Not enough free disk space");
  expect(errorCode(error)).toBe("no_space");
});

test("errors without details get a plain message and no code", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 500, json: async () => "oops" })));
  const error = await api.get("/api/hello").catch((err: unknown) => err);
  expect(errorText(error)).toContain("status 500");
  expect(errorCode(error)).toBeNull();
});
