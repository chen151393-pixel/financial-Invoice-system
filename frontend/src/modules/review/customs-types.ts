import type { ApprovalProgress } from "./approval-progress";

// 与后端 /api/review/customs-receipts 的响应一致；数量、金额为十进制字符串，前端不重算。
export type CustomsMatchStatus = "matched" | "split_matched" | "different" | "ns_missing" | "ns_duplicate";
// 差异类型：一张回执可同时属于多类，均为“有差异”的子集
export type CustomsDifferenceKind = "quantity_mismatch" | "unit_mismatch" | "total_mismatch" | "line_missing";
// matched 含拆行一致；ns_missing 含 NS 报关单重号（后端合并筛选）
export type CustomsFilter = "all" | "matched" | "different" | "ns_missing" | "approved";
export type CustomsGroupStatus =
  | "matched"
  // 一对一行数量一致、总价不同；报关单为有差异，不能自动审核
  | "total_mismatch"
  | "split"
  | "merged"
  | "quantity_mismatch"
  | "unit_mismatch"
  | "missing_in_ns"
  | "missing_in_customs";

export interface CustomsItem {
  itemNo: string;
  hsCode: string;
  name: string;
  specification: string;
  contractNo: string;
  taxType: string;
  checkStatus: string;
  quantity: string;
  unit: string;
  currency: string;
  total: string;
  usdFob: string;
  legalQuantity: string;
  legalUnit: string;
  customsDoc: string;
  usageFlag: string;
}

export interface CustomsNsLine {
  id: number;
  lineNo: string;
  itemCode: string;
  name: string;
  specification: string;
  quantity: string;
  unit: string;
  currency: string;
  total: string;
}

export interface CustomsCompareGroup {
  status: CustomsGroupStatus;
  label: string;
  note: string;
  // 后端判定的一致类（一致、拆行一致、合并一致）
  consistent: boolean;
  nsLines: CustomsNsLine[];
  items: CustomsItem[];
  totalMismatch: boolean | null;
}

// saved：已随 NS 报关单保存；empty：回执未提供；pending：待匹配到 NS 报关单后关联
export interface CustomsConsignee {
  value: string;
  state: "saved" | "empty" | "pending";
  label: string;
  note: string;
}

export interface CustomsReceipt {
  approvalProgress?: ApprovalProgress | null;
  id: number;
  declarationNo: string;
  exportDate: string;
  taxType: string;
  customsDoc: string;
  usageFlag: string;
  itemCount: number;
  nsLineCount: number | null;
  nsRecordNo: string;
  consignee: CustomsConsignee;
  status: CustomsMatchStatus;
  statusLabel: string;
  statusNote: string;
  totalComparison: "matched" | "different" | "partial" | "not_compared";
  matchedAt: string;
  importedAt: string;
  fileName: string;
  revision: number;
  groups: CustomsCompareGroup[];
  approval: {
    token: string;
    approved: boolean;
    label: string;
    allowed: boolean;
    autoAllowed: boolean;
    reason: string;
    approvedBy: string;
    approvedAt: string;
    note: string;
  };
}

export interface CustomsApproveResult {
  approved: { id: number; declarationNo: string; reason: string }[];
  skipped: { id: number; declarationNo: string; reason: string }[];
}

export interface CustomsCounts {
  receipts: number;
  items: number;
  matched: number;
  splitMatched: number;
  different: number;
  nsMissing: number;
  approved: number;
  // 有差异按类型拆分（后端计数，可重叠）
  quantityMismatch: number;
  unitMismatch: number;
  totalMismatch: number;
  lineMissing: number;
}

export interface CustomsReceiptList {
  items: CustomsReceipt[];
  counts: CustomsCounts;
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

/** 当前保留回执按来源归组的导入记录。 */
export interface CustomsImportSource {
  fileName: string;
  importedBy: string;
  importedByName: string;
  importedAt: string;
  receiptCount: number;
}

export interface CustomsImportHistory {
  items: CustomsImportSource[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

export interface CustomsSearch {
  declarationNo: string;
  name: string;
  consignee: string;
  exportFrom: string;
  exportTo: string;
  // 差异类型，与状态筛选同时生效；空为不限
  difference: "" | CustomsDifferenceKind;
}

export interface CustomsReceiptQuery extends CustomsSearch {
  exactDeclarationNo?: string;
  status: CustomsFilter;
  page: number;
  pageSize: number;
}

export interface ImportedDeclaration {
  declarationNo: string;
  itemCount: number;
  result: "created" | "replaced" | "unchanged";
  resultLabel: string;
  status: CustomsMatchStatus;
  statusLabel: string;
  consignee: CustomsConsignee;
}

export interface CustomsImportResult {
  fileName: string;
  rows: number;
  columns: string[];
  ignoredColumns: string[];
  created: number;
  replaced: number;
  unchanged: number;
  declarations: ImportedDeclaration[];
}
export type CustomsImportJob = {
  id: string;
  fileName: string;
  status: "pending" | "running" | "completed" | "failed";
  statusLabel: string;
  error: string;
  result: CustomsImportResult | null;
};
