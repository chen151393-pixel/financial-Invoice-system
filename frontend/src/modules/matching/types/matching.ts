// 与后端 matching 模块 VO 一致；金额、数量、置信度为十进制字符串，前端不重算。
export type Capability = { allowed: boolean; reason: string };
export type Tier = "high" | "medium" | "low" | "manual";
export type AllocationStatus = "proposed" | "confirmed" | "rejected" | "cancelled";

export type Check = {
  key: string;
  label: string;
  invoiceValue: string | null;
  purchaseValue: string | null;
  result: "match" | "partial" | "mismatch" | "missing";
  difference: string | null;
  note: string;
};

export type PurchaseSide = {
  purchaseBasisId: string | null;
  purchaseLineId: string;
  orderNo: string;
  supplier: string;
  company: string;
  item: string;
  specification: string;
  unit: string;
  currency: string;
  currencyNote: string;
  expectedQuantity: string | null;
  expectedAmount: string | null;
  receivedQuantity: string | null;
  receivedAmount: string | null;
  remainingQuantity: string | null;
  remainingAmount: string | null;
  recordNumber: string;
  taskId: string | null;
};

export type Allocation = {
  invoiceVersionId: string | null;
  currentInvoiceVersionId: string | null;
  purchaseBasisId: string | null;
  purchaseQuantity: string | null;
  verificationStatus: string;
  verificationIssues: string[];
  reverify: Capability;
  replace: Capability;
  id: string;
  invoiceItemId: string;
  purchaseLineId: string;
  quantity: string;
  amount: string;
  status: AllocationStatus;
  statusLabel: string;
  confidence: string | null;
  tier: Tier;
  checks: Check[];
  exceedsExpected: boolean;
  closesPurchaseLine: boolean;
  proposedBy: string;
  proposedAt: string;
  reviewedBy: string | null;
  reviewedAt: string | null;
  reviewNote: string | null;
  cancelledBy: string | null;
  cancelledAt: string | null;
  cancelReason: string | null;
  purchase: PurchaseSide | null;
  confirm: Capability;
  noteReasons: string[];
  reject: Capability;
  cancel: Capability;
};

export type InvoiceItem = {
  active: boolean;
  id: string;
  lineNo: string | null;
  item: string | null;
  specification: string | null;
  unit: string | null;
  quantity: string | null;
  amount: string | null;
  confirmedQuantity: string;
  confirmedAmount: string;
  allocations: Allocation[];
};

export type InvoiceMatching = {
  invoice: {
    versionId: string | null;
    detailStatus: string;
    id: string;
    number: string;
    date: string | null;
    seller: string | null;
    buyer: string | null;
    status: string;
    statusLabel: string;
    currency: string;
    gross: string | null;
    remark: string | null;
  };
  items: InvoiceItem[];
  generate: Capability;
};

export type QueueRow = {
  allocation: Allocation;
  invoiceId: string;
  invoiceNumber: string;
  seller: string | null;
  itemName: string | null;
};
export type Queue = {
  rows: QueueRow[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  counts: Record<"all" | "high" | "medium" | "low", number>;
  // 待审核建议涉及的供应商（按子采购单），供筛选
  suppliers?: { id: string; name: string }[];
};
export type QueueQuery = {
  tier: "all" | "high" | "medium" | "low";
  // 供应商与开票日期筛选；空字符串为不限，日期为 YYYY-MM-DD
  supplierId: string;
  invoiceFrom: string;
  invoiceTo: string;
  page: number;
  pageSize: number;
};

export type MatchingSummary = {
  invoiceId: string;
  status: "none" | "proposed" | "partial" | "confirmed" | "needs_review";
  label: string;
  tier: Tier | null;
  proposed: number;
  confirmed: number;
};

export type Candidate = {
  purchase: PurchaseSide;
  checks: Check[];
  confidence: string;
  tier: Tier;
  block: string;
};

export type Conversion = {
  conversionNumerator: string;
  conversionDenominator: string;
  conversionEvidence: string;
};
export type ConfirmBody = Partial<Conversion> & {
  note: string;
  closesPurchaseLine?: boolean;
  invoiceVersionId?: string | null;
  purchaseBasisId?: string | null;
};
export type ManualBody = ConfirmBody & {
  requestId: string;
  invoiceId: string;
  invoiceItemId: string;
  purchaseLineId: string;
  quantity: string;
  amount: string;
};

// 中文文案只在这里维护一份。
export const tierLabels: Record<Tier, string> = { high: "高", medium: "中", low: "低", manual: "人工" };
export const resultLabels: Record<Check["result"], string> = {
  match: "一致",
  partial: "部分一致",
  mismatch: "不一致",
  missing: "未提供",
};
