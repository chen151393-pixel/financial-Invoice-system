import type { Capability, Conversion } from "./matching";

export type OrderAllocationPreview = {
  invoiceItemId: string;
  purchaseLineId: string;
  purchaseBasisId: string;
  item: string;
  invoiceUnit: string;
  purchaseUnit: string;
  invoiceQuantity: string;
  purchaseQuantity: string;
  amount: string;
};

export type OrderCandidate = {
  purchaseOrderId: string;
  orderNo: string;
  parentOrderNo: string;
  account: string;
  supplier: string;
  company: string;
  currency: string;
  lineCount: number;
  remainingAmount: string | null;
  remainingQuantity: string | null;
  unit: string;
  orderMatched: boolean;
  fingerprint: string;
  warnings: string[];
  confirm: Capability;
  allocations: OrderAllocationPreview[];
};

export type OrderCandidates = { rows: OrderCandidate[]; total: number; page: number; pages: number };
export type OrderConfirmBody = Conversion & {
  requestId: string;
  invoiceId: string;
  invoiceVersionId: string | null;
  purchaseOrderId: string;
  fingerprint: string;
  note: string;
};
