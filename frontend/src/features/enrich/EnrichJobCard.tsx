// The transcripts job card: the shared JobCard plus which speech model ran where.
import JobCard from "../../components/JobCard";
import type { Job } from "../../lib/jobs";
import type { EnrichResult } from "./enrichApi";

export default function EnrichJobCard({ job }: { job: Job }) {
  const result = job.result as EnrichResult | null;
  const nothingWorked =
    result !== null &&
    result.failed + result.later > 0 &&
    result.transcribed + result.no_speech + result.details_only === 0;
  const detail = result?.device
    ? `Speech model: ${result.model}, running on ${result.device === "gpu" ? "the graphics card" : "the processor"}.`
    : undefined;
  return <JobCard job={job} name="transcripts job" detail={detail} warn={nothingWorked} />;
}
