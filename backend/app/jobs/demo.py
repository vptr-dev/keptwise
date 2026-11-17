"""A fake 10-second job for the developer page, to see live progress."""

from __future__ import annotations

import time
from typing import Any

from app.jobs.runner import JobContext

STEPS = 20
STEP_SECONDS = 0.5


def run_demo_job(ctx: JobContext) -> dict[str, Any]:
    seconds = float(ctx.params.get("step_seconds", STEP_SECONDS))
    for step in range(1, STEPS + 1):
        ctx.check()
        time.sleep(seconds)
        ctx.progress(step, STEPS, f"Step {step} of {STEPS}")
    return {"message": f"Finished all {STEPS} steps"}
