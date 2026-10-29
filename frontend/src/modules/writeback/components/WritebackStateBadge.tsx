import { Badge, type Tone } from "../../../shared/components/ui";
import type { TaskSummary } from "../types";

const tones: Record<string, Tone> = {
  queued: "neutral",
  waiting_bill: "info",
  needs_confirmation: "warning",
  needs_preview: "warning",
  ready: "info",
  executing: "progress",
  applied: "success",
  conflict: "warning",
  partial: "warning",
  unknown: "warning",
  blocked: "danger",
  stale: "neutral",
};
export function WritebackStateBadge({ task }: { task: TaskSummary }) {
  return <Badge tone={tones[task.state] ?? "neutral"}>{task.stateLabel}</Badge>;
}
