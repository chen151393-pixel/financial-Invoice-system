import type { Tone } from "../../../shared/components/ui";
import type { ReceivableStageCount } from "../types";

// 后端阶段、资料状态 → 徽标语义色；文字始终来自后端，颜色只作辅助。
const STAGE_TONES: Record<ReceivableStageCount["stage"], Tone> = {
  all: "neutral",
  unregistered: "warning",
  collected: "progress",
  remit: "info",
  unpaid: "warning",
  partial: "progress",
  settled: "success",
  issue: "danger",
  alert: "danger",
};

const DOCUMENT_TONES: Record<string, Tone> = {
  pending: "warning",
  stale: "warning",
  pending_bill: "warning",
  pending_contract: "warning",
  complete: "info",
  ready: "success",
  kept: "success",
};

export const stageTone = (stage: ReceivableStageCount["stage"]): Tone => STAGE_TONES[stage] ?? "neutral";
export const documentTone = (status: string): Tone => DOCUMENT_TONES[status] ?? "neutral";
