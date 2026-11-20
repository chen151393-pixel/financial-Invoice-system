import type { Action, BatchDetail } from "../types";
import type { StepItem } from "../../../shared/components/ui";
export type HkStageKey =
  | "open"
  | "register"
  | "collected"
  | "documents_ready"
  | "settled"
  | "cancelled"
  | "all";
export interface HkStage {
  key: HkStageKey;
  label: string;
  value: string;
  note: string;
  tone: "primary" | "warning" | "progress" | "info" | "success" | "neutral";
}
export interface HkPending {
  declarationNo: string;
  recordNo: string;
  consignee: string;
  exportCompany: string;
  currency: string;
  amount: string;
  exportDate: string;
  waitingLabel: string;
  select: Action;
}
export interface HkBatch {
  batch: BatchDetail;
  waitingLabel: string;
  overdue: boolean;
  issue: string;
  notice: string;
  documents: { label: string; ready: boolean; description: string }[];
  steps: StepItem[];
  packageUrl: string;
  package: Action;
  primaryLabel: string;
  primaryAction: "documents" | "remit" | "package" | "view";
}
export interface HkWorkbench {
  stages: HkStage[];
  pending: HkPending[];
  pendingTotal: number;
  pendingPage: number;
  pendingPageCount: number;
  batches: HkBatch[];
  batchTotal: number;
  page: number;
  pageCount: number;
  asOf: string;
}
export interface HkWorkbenchQuery {
  stage: HkStageKey;
  consignee: string;
  keyword: string;
  page: number;
  pageSize: number;
  pendingPage: number;
  pendingPageSize: number;
}

export interface HkReceiptCheck {
  currency: string;
  declaredTotal: string;
  arrivedTotal: string;
  difference: string;
  balanced: boolean;
  warnings: string[];
  submit: Action;
}
