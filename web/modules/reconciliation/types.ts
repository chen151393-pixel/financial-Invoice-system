// 后端提供已归组的同次读取结果；页面不重新聚合或计算金额。
export const comparisonColumns = [
  "报关单号",
  "申报日期",
  "关联PL单号",
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
] as const;

export type ComparisonCells = readonly [
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  string,
  "待确认",
  string,
];

export interface ComparisonRow {
  id: string;
  cells: ComparisonCells;
  headId: string;
  currency: string;
}

export interface ComparisonGroup {
  id: string;
  pl: string;
  company: string;
  status: string;
  summary: string;
  customs: readonly ComparisonRow[];
  purchases: readonly ComparisonRow[];
}

export interface ComparisonResult {
  pl: string;
  company: string;
  account: string;
  queriedAt: string;
  source: "netsuite-rest";
  groups: readonly ComparisonGroup[];
  warnings: readonly string[];
  download: { filename: string; contentBase64: string; mediaType: string } | null;
}

export type ComparisonState =
  | { kind: "ready"; result: ComparisonResult }
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string };
