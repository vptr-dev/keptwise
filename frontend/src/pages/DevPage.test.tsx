import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { FakeEventSource, fakeBackend, makeJob } from "../test/fakeBackend";
import DevPage from "./DevPage";

const stats = {
  path: "C:/data/saves.db",
  data_dir: "C:/data",
  size_bytes: 4096,
  schema_version: 1,
  tables: { items: 3, jobs: 0 },
  items_by_status: {},
};

const fakeJob = (status: string, progress: number) =>
  makeJob({ id: 7, kind: "demo", title: "Fake 10-second job", status, progress, total: 20, message: `Step ${progress} of 20` });

test("shows stats and live progress of the fake job", async () => {
  vi.stubGlobal("EventSource", FakeEventSource);
  fakeBackend({
    "GET /api/dev/stats": stats,
    "GET /api/jobs": [],
    "POST /api/dev/fake-job": fakeJob("queued", 0),
  });

  render(<DevPage />);
  expect(await screen.findByText("Rows in items")).toBeInTheDocument();

  fireEvent.click(screen.getByText("Start fake 10-second job"));
  act(() => FakeEventSource.last?.emit("job", fakeJob("running", 5)));
  expect(await screen.findByText("Step 5 of 20")).toBeInTheDocument();
  expect(screen.getByTestId("job-status-7")).toHaveTextContent("running");
  expect(screen.getByRole("progressbar", { name: "Fake 10-second job" })).toHaveAttribute("aria-valuenow", "25");
});
