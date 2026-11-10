// 与后端 /api/review 的响应一致；金额、数量为十进制字符串，前端不重算。
// unshipped：未出库。自 2026-10-23 起拉取时即跳过，列表不再返回；保留类型以显示后端兜底拒绝。
export type ReviewStatus = "pending" | "approved" | "unshipped";
// margin_alert：待审核且单价超容差或原始/报关口径不一致；auto：待审核且满足可自动审核条件（后端判定）
// unit_mismatch：申报幅度异常中含单位不一致报关行的待审核单据
export type ReviewFilter = "all" | "pending" | "approved" | "margin_alert" | "unit_mismatch" | "auto";
export interface UnitPriceMargin {
  // 后端比较同一报关行的 NS 单价与报关单价；两价折人民币后判断固定容差。
  margin?: string;
  // unit_mismatch / quantity_mismatch：报关行原始口径与报关口径单位或数量不一致，后端不计算幅度
  marginStatus?: "ok" | "negative" | "unavailable" | "unit_mismatch" | "quantity_mismatch";
  marginNote?: string;
  declaredUnitPriceCny?: string;
  originalUnitPriceCny?: string;
  originalPriceUnit?: string;
  declaredPriceUnit?: string;
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
  // 报关行原始口径（NS 数量、单价；单位见 originalPriceUnit），页面列名“采购单价”
  originalQuantity?: string;
  originalPrice?: string;
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
    | "unitMismatch"
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
  createdFrom?: string;
  createdTo?: string;
  supplierName?: string;
  recordNo?: string;
  // 真实报关单号，与 CD 号不同
  declarationNo?: string;
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
