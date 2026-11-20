import type { HkPending } from "./hk-workbench";
import type { Action, CreateBatchBody } from "../types";
export interface HkReceiptFields {
  receivedOn: string;
  receivedAmount: string;
  receivedFee: string;
  payer: string | null;
  receivingAccount: string;
  receivedReference: string;
  note: string;
}
export interface BankSlipUpload {
  fileName: string;
  content: string;
}
export interface HkRegistrationCheck {
  rows: HkPending[];
  currency: string;
  consignee: string;
  declaredTotal: string;
  amount: string;
  fee: string;
  arrivedTotal: string;
  difference: string;
  balanced: boolean;
  accounts: string[];
  checks: { key: string; label: string; detail: string; state: "success" | "warning" | "error" }[];
  warnings: string[];
  submit: Action;
}
export type RegisterHkBody = CreateBatchBody & { bankSlip?: BankSlipUpload | null };
export interface HkReceiptDraft {
  id: string;
  fields: HkReceiptFields;
  bankSlip: BankSlipUpload | null;
}
