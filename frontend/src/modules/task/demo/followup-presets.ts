import type { StepItem } from "../../../shared/components/ui/Stepper";
import type { BoardNode, BoardNodeKey } from "../types/board";

// 仅为原型提供预置展示状态，不根据金额推导正式节点或进度。
export const demoNodes: BoardNode[] = [
  { key: "documents", label: "待存合同", hint: "合同尚未归档", count: 0 },
  { key: "notification", label: "待通知供应商", hint: "合同就绪，等待通知", count: 0 },
  { key: "invoices", label: "待供应商开票", hint: "尚无已确认收票；候选发票不计入进度", count: 3 },
  { key: "comparison", label: "部分收票", hint: "已确认部分发票，等待剩余收票", count: 1 },
  { key: "completion", label: "待补资料", hint: "收票完成，仍缺归档资料", count: 1 },
  { key: "done", label: "已完成", hint: "收票与资料均已完成", count: 0 },
];
const waitingSteps: StepItem[] = [
  { key: "review", label: "财务审核", state: "done" },
  { key: "documents", label: "合同归档", state: "done" },
  { key: "notification", label: "通知供应商", state: "done" },
  { key: "invoices", label: "供应商开票", state: "current" },
  { key: "comparison", label: "收票确认", state: "waiting" },
  { key: "completion", label: "资料齐全", state: "waiting" },
];
const partialSteps: StepItem[] = [
  ...waitingSteps.slice(0, 3),
  { key: "invoices", label: "供应商开票", state: "done" },
  { key: "comparison", label: "收票确认", state: "current" },
  { key: "completion", label: "资料齐全", state: "waiting" },
];
const documentsSteps: StepItem[] = [
  ...partialSteps.slice(0, 4),
  { key: "comparison", label: "收票确认", state: "done" },
  { key: "completion", label: "资料齐全", state: "current" },
];
export const followupPresets: Record<string, { node: BoardNodeKey; percent: string; steps: StepItem[] }> = {
  "sample-01": { node: "invoices", percent: "0", steps: waitingSteps },
  "sample-02": { node: "invoices", percent: "0", steps: waitingSteps },
  "sample-03": { node: "comparison", percent: "50", steps: partialSteps },
  "sample-04": { node: "invoices", percent: "0", steps: waitingSteps },
  "sample-05": { node: "completion", percent: "100", steps: documentsSteps },
};
