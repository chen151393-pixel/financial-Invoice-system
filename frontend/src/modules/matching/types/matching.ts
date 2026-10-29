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
  // 票面展示：单价、不含税金额、税率（如“13%”）、税额
  unitPrice: string | null;
  net: string | null;
  taxRate: string | null;
  tax: string | null;
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
  paper: {
    invoiceType: string | null;
    buyerTaxNo: string | null;
    sellerTaxNo: string | null;
    net: string | null;
    tax: string | null;
    gross: string | null;
  };
  items: InvoiceItem[];
  // 待审核的整单建议；组内记录也出现在各发票行 allocations 中
  groups: MatchingGroup[];
  generate: Capability;
};

export type GroupLine = {
  purchaseLineId: string;
  orderNo: string;
  item: string;
  specification: string;
  unit: string;
  quantity: string;
  amount: string;
  taxRate: string | null;
};

// 发票行与所选整张子采购单合计的比对，后端实时重算
export type GroupItem = {
  invoiceItemId: string;
  checks: Check[];
  confidence: string;
  tier: Tier;
  quantity: string;
  amount: string;
  lines: GroupLine[];
};

export type MatchingGroup = {
  id: string;
  orders: {
    purchaseOrderId: string;
    orderNo: string;
    parentOrderNo: string;
    supplier: string;
    company: string;
    lineCount: number;
  }[];
  items: GroupItem[];
  confidence: string;
  tier: Tier;
  noteReasons: string[];
  confirm: Capability;
  reject: Capability;
  allocationIds: string[];
};

export type QueueRow = {
  allocation: Allocation;
  invoiceId: string;
  invoiceNumber: string;
  seller: string | null;
  itemName: string | null;

  // 异常分类（价格、数量、单位等）；空表示正常
  anomalies?: string[];
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
  notice?: string;
};
export type QueueQuery = {
  invoiceNo: string;
  supplierName: string;
  tier: "all" | "high" | "medium" | "low";
  // 只看异常 / 只看正常：异常为需要填写说明或当前不能通过的建议
  anomaly: "all" | "abnormal" | "normal";
  // 供应商与开票日期筛选；空字符串为不限，日期为 YYYY-MM-DD
  supplierId: string;
  invoiceFrom: string;
  invoiceTo: string;
  page: number;
  pageSize: number;
};
export type InvoiceQueueRow = {
  invoice: InvoiceMatching["invoice"];
  proposalCount: number;
  purchaseOrders: string[];
  confidence: string;
  tier: Tier;
  anomalies: string[];
  batch: Capability;
  batchIds: string[];
};
export type InvoiceQueue = Omit<Queue, "rows"> & { rows: InvoiceQueueRow[] };

// 发票匹配状态（后端 invoice_match_policy 判定）；excluded 为红字、已被红冲、作废等不参与比对的发票
export type MatchStatus = "confirmed" | "partial" | "proposed" | "needs_review" | "none" | "excluded";
export type MatchingSummary = {
  invoiceId: string;
  status: MatchStatus;
  label: string;
  tier: Tier | null;
  proposed: number;
  confirmed: number;
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

// 中文文案只在这里维护一份。
export const tierLabels: Record<Tier, string> = { high: "高", medium: "中", low: "低", manual: "人工" };
export const resultLabels: Record<Check["result"], string> = {
  match: "一致",
  partial: "部分一致",
  mismatch: "不一致",
  missing: "未提供",
};

// 进项发票按匹配状态筛选的列表：list 为发票列表分页结构（由调用方给出类型），counts 不受所选匹配状态影响
export type InvoiceMatchFilters = {
  q?: string;
  invoice_no?: string;
  seller_name?: string;
  seller_tax_no?: string;
  account: string;
  status: string;
  date_from: string;
  date_to: string;
  matchStatus: "all" | MatchStatus;
  page: number;
  pageSize: number;
};
export type InvoiceMatchList<List> = {
  list: List;
  counts: Record<"all" | MatchStatus, number>;
  summaries: MatchingSummary[];
  notice: string;
};
