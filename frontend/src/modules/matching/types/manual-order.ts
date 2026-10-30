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
  // 子采购单全部明细；整单关联，记账数由后端生成
  lines: PurchaseSide[];
};

export type ManualOrderCandidates = { rows: ManualOrderCandidate[]; total: number };

// 一张子采购单只由一张发票开具：整单关联，不提交逐条明细数量（2026-10-30 整单规则）
export type ManualOrderBody = {
  requestId: string;
  invoiceId: string;
  invoiceItemId: string;
  purchaseOrderId: string;
  invoiceVersionId: string | null;
  note: string;
  replaceAllocationId: string | null;
  replaceReason: string;
};
