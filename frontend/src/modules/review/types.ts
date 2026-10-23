// 与后端 /api/review 的响应一致；金额、数量为十进制字符串，前端不重算。
// unshipped：未出库（缺真实报关单号或无关联子采购单），不计入"全部"，单独筛选查看。
export type ReviewStatus = "pending" | "approved" | "unshipped";
export type ReviewFilter = "all" | ReviewStatus;
export interface PurchaseLine {
  id: string;
  name: string;
  model: string;
  parent: string;
  child: string;
  supplier: string;
  quantity: string;
  unit: string;
  price: string;
  amount: string;
  currency: string;
  note: string;
  scope?: "declared" | "order";
}
export interface CustomsLine {
  id: string;
  lineNo: number;
  name: string;
  model: string;
  quantity: string;
  unit: string;
  price: string;
  amount: string;
  currency: string;
  purchaseCount: number;
  purchaseLines: PurchaseLine[];
}
export interface ComparisonGroup {
  currencyEvidenceSummary?: string[];
  currencyChecks: {
    purchaseOrderId: string;
    orderNumber: string;
    currency: string;
    allowed: boolean;
    reason: string;
  }[];
  id: string;
  contentSha256: string;
  account: string;
  recordNumber: string;
  declaration: string;
  pl: string;
  company: string;
  customsCount: number;
  purchaseCount: number;
  customsLines: CustomsLine[];
  unlinkedLines: PurchaseLine[];
  warnings: string[];
  review: {
    status: ReviewStatus;
    label: string;
    allowed: boolean;
    reason: string;
    revision?: number | null;
    reviewedAt: string | null;
    reviewedBy: string | null;
    note: string;
  };
}
export interface ComparisonResult {
  groups: ComparisonGroup[];
  counts: Record<ReviewFilter | "customs" | "purchase" | "shown", number>;
  notices: string[];
  accounts: string[];
  suppliers: { id: string; name: string }[];
  page: number;
  pageSize: number;
  total: number;
  pages: number;
}
export interface DeclarationListQuery {
  keyword: string;
  account: string;
  supplierId: string;
  status: ReviewFilter;
  page: number;
  pageSize: number;
}
export interface BatchItemResult {
  id: string;
  recordNumber: string;
  reason: string;
}
export interface BatchApproveResult {
  approved: BatchItemResult[];
  skipped: BatchItemResult[];
}
export type ComparisonState =
  | { kind: "ready"; result: ComparisonResult }
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string };

export type CurrencyEvidence = { purchaseOrderId: string; currency: string; reference: string; note: string };
