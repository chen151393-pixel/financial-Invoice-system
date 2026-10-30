import type { Tone } from "../../../shared/components/ui";
import type { Action } from "./background";

export type NsPlanKind = "customs-declarations" | "sub-purchase-orders";
export type NsPlan = {
  revision: number;
  enabled: boolean;
  nextRunAt: string | null;
  kinds: NsPlanKind[];
  times: string[];
  lookbackDays: number;
  /** 后端自动暂停的原因（结果待核实、保存人失去管理员角色）；重新保存后清除。 */
  pausedReason: string | null;
};
export type NsPlanConfig = {
  plan: NsPlan;
  submit: Action;
  pause: Action;
  kindOptions: { value: NsPlanKind; label: string; hint: string }[];
  coverage: string;
  timezone: string;
};
export type NsBatch = {
  requestId: string;
  recordType: "plan" | "manual";
  kind: NsPlanKind;
  kindLabel: string;
  phase: string;
  label: string;
  trigger: string;
  startDate: string | null;
  endDate: string | null;
  createdAt: string;
  finishedAt: string | null;
  message: string;
  fetched: number;
  created: number;
  updated: number;
  failed: number;
};
export type NsBatchPage = {
  index: number;
  requestId: string;
  status: string;
  statusLabel: string;
  count: number | null;
  saved: number;
  failed: number;
  skipped: number;
  unknown: number;
  failures: { id: string; number: string; status: string; reason: string }[];
  error: string | null;
  progress: {
    state: string;
    label: string;
    completed: number | null;
    total: number | null;
    elapsedSeconds: number;
  } | null;
  createdAt: string;
  updatedAt: string;
};
export type NsBatchDetail = NsBatch & { pages: NsBatchPage[]; poll: boolean };
export type NsBatchList = {
  items: NsBatch[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  counts: Record<string, number>;
  plan: { enabled: boolean; nextRunAt: string | null };
};

// 后端状态到徽标语义色的映射；文字始终使用后端返回的中文标签。
const tones: Record<string, Tone> = {
  queued: "info",
  running: "info",
  completed: "success",
  partial: "progress",
  interrupted: "warning",
  unknown: "warning",
  failed: "danger",
};
export const statusTone = (status: string): Tone => tones[status] ?? "neutral";

export const nsPhaseOptions = [
  ["", "全部状态"],
  ["queued", "等待执行"],
  ["running", "执行中"],
  ["completed", "已完成"],
  ["partial", "部分成功"],
  ["failed", "失败"],
  ["unknown", "结果待核实"],
] as const;
