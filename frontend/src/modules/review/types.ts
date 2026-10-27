// 与后端 /api/review 的响应一致；金额、数量为十进制字符串，前端不重算。
// unshipped：未出库。自 2026-10-23 起拉取时即跳过，列表不再返回；保留类型以显示后端兜底拒绝。
export type ReviewStatus = "pending" | "approved" | "unshipped";
export type ReviewFilter = "all" | "pending" | "approved";
export interface UnitPriceMargin {
  // 后端按人民币报关单价与合并采购单价（含税总金额 / 总数量）比较，前端只展示。
  margin?: string;
  marginStatus?: "ok" | "negative" | "unavailable";
  marginNote?: string;
  declaredUnitPriceCny?: string;
  combinedPurchaseUnitPrice?: string;
}
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
  members?: PurchaseLine[];
}
export interface CustomsLine extends UnitPriceMargin {
  id: string;
  parent?: string;
  originPlace?: string;
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
  salesOrders?: string;
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
  // changed：待审核中来源已变化的张数；approvedThisMonth：北京时间本月审核通过张数
  counts: Record<ReviewFilter | "customs" | "purchase" | "shown" | "changed" | "approvedThisMonth", number>;
  notices: string[];
  accounts: string[];
  suppliers: { id: string; name: string }[];
  page: number;
  pageSize: number;
  total: number;
  pages: number;
}
// 上线只同步 NS 正式环境，不再按 NS 账套筛选（后端参数保留为可选，不传即不限）
export interface DeclarationListQuery {
  keyword: string;
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
