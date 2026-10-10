import type { PlSearchCriteria } from "./types";

// 与 /api/source/pl-comparison 的展示契约一致；保留NS顺序和来源文本。
export const sourceColumns = [
  "报关单号",
  "申报日期",
  "关联 PL 单号",
  "销售单号",
  "母采购单号",
  "子采购单号",
  "货源地",
  "供应商",
  "申报公司抬头",
  "开票品名",
  "型号",
  "数量",
  "单位",
  "含税单价",
  "总金额",
  "单价",
  "报关币种",
] as const;

export interface SourceComparisonRow {
  id: string;
  side: "customs" | "purchase";
  cells: string[];
  note: string;
  missingCells: number[];
  currency: string;
}

export interface SourceComparisonResult {
  contractVersion: 1 | 2 | 3;
  source: "netsuite-script";
  complete: true;
  account: string;
  requestId: string;
  query: PlSearchCriteria;
  readCompletedAt: string;
  counts: { customs: number; purchase: number; declarations: number; groups: number };
  groups: {
    id: string;
    title: string;
    rows: SourceComparisonRow[];
    customsCount: number;
    purchaseCount: number;
    warnings: string[];
  }[];
}

export type SourceComparisonState =
  | { kind: "ready"; result: SourceComparisonResult }
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string };
