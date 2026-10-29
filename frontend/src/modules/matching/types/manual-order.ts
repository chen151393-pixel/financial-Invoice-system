import type { Check, PurchaseSide, Tier } from "./matching";

// 与后端 /api/matching/manual-orders 一致：候选一行一张整张子采购单；合计、比对、置信度和限制均来自后端。
export type ManualOrderCandidate = {
  purchaseOrderId: string;
  orderNo: string;
  parentOrderNo: string;
  supplier: string;
  company: string;
  recordNumbers: string[];
  currency: string;
  unit: string;
  remainingQuantity: string | null;
  remainingAmount: string | null;
  orderMatched: boolean;
  confidence: string;
  tier: Tier;
  checks: Check[];
  block: string;
  // 选中后展示的明细；表单默认值取各行剩余应开
  lines: PurchaseSide[];
};

export type ManualOrderCandidates = { rows: ManualOrderCandidate[]; total: number };

export type OrderLineShare = { purchaseLineId: string; quantity: string; amount: string };

// 须提交该单全部可分配明细；本票不开的明细数量与金额填 0
export type ManualOrderBody = {
  requestId: string;
  invoiceId: string;
  invoiceItemId: string;
  purchaseOrderId: string;
  invoiceVersionId: string | null;
  lines: OrderLineShare[];
  note: string;
  replaceAllocationId: string | null;
  replaceReason: string;
};
