// 与后端 /api/review 的响应一致；金额、数量为十进制字符串，前端不重算。
// unshipped：未出库。自 2026-10-23 起拉取时即跳过，列表不再返回；保留类型以显示后端兜底拒绝。
export type ReviewStatus = "pending" | "approved" | "unshipped";
// margin_alert：待审核且采购单价超出报关单价容差；auto：待审核且满足可自动审核条件（后端判定）
export type ReviewFilter = "all" | "pending" | "approved" | "margin_alert" | "auto";
export interface UnitPriceMargin {
  // 后端按人民币申报单价与采购金额折算报关单价（含税总金额 / 总报关数量）比较。
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
  purchaseQuantity?: string;
  purchaseUnit?: string;
  amount: string;
  currency: string;
  salesOrderExchangeRate?: string;
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
  // NS 未填申报单价时 price 为后端按报关金额 ÷ 报关数量的试算值，页面标注“试算”
  priceEstimated?: boolean;
  amount: string;
  currency: string;
  purchaseCount: number;
  purchaseLines: PurchaseLine[];
}
export interface ComparisonGroup {
  purchaseOrderNumbers?: string[];
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
  // 任一报关行采购单价超出人民币报关单价容差（后端判定）
  marginAlert?: boolean;
  calculationStatus?: "ready" | "pending" | "failed";
  calculatedAt?: string | null;
  // 可自动审核通过的预判：只用于提示与筛选，审核仍需确认
  autoReview?: { eligible: boolean; reasons: string[] };
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
  counts: Record<
    | "all"
    | "pending"
    | "approved"
    | "customs"
    | "purchase"
    | "shown"
    | "changed"
    | "approvedThisMonth"
    | "marginAlert"
    | "autoApprovable",
    number
  >;
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
  supplierName?: string;
  recordNo?: string;
  purchaseOrderNo?: string;
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
