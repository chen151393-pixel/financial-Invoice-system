import type { BatchDetail, Bill, Contract, PlannedContract, ReceivableItem } from "../types";

export interface ReceiptApplication {
  receiptId: number;
  date: string;
  reference: string;
  receiptAmount: string;
  appliedAmount: string;
  payer: string;
  thirdParty: boolean;
}
export interface AllocationRow {
  declarationNo: string;
  exportDate: string;
  amount: string;
  receivedAmount: string;
  outstandingAmount: string;
  current: boolean;
  receipts: ReceiptApplication[];
}
export interface DeclarationDetail {
  item: ReceivableItem;
  steps: {
    key: string;
    label: string;
    description: string;
    state: "done" | "current" | "waiting";
    percent: number;
  }[];
  batch: BatchDetail | null;
  allocations: AllocationRow[];
  ledgerBalance: string;
  ledgerNote: string;
  documents: {
    groupId?: number | null;
    scopeKind: "batch" | "single" | "group" | "none";
    scopeLabel: string;
    scopeNumbers: string[];
    note: string;
    original: {
      statusLabel: string;
      archived: boolean;
      files: { name: string; url: string }[];
      note: string;
    };
    bills: Bill[];
    contracts: { planned: PlannedContract | null; contract: Contract | null; label: string }[];
    issues: string[];
    warnings: string[];
  };
  events: { at: string; actor: string; description: string }[];
  asOf: string;
}
