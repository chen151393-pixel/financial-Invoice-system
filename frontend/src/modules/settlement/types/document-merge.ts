import type { Action } from "../types";
import type { DocumentGroup } from "./document-group";
export type MergeMember = DocumentGroup["members"][number];
export interface MergeCandidate extends MergeMember {
  groupId: number | null;
  groupNo: string;
  source: boolean;
  sharedBill: boolean;
  select: Action;
}
export interface DocumentMergeQuery {
  sourceDeclarationNo: string;
  keyword: string;
  exportFrom: string | null;
  exportTo: string | null;
  page: number;
  pageSize: number;
}
export interface MergeCandidates {
  source: MergeCandidate;
  items: MergeCandidate[];
  total: number;
  page: number;
  pageSize: number;
}
export interface MergeSelection {
  sourceDeclarationNo: string;
  declarationNos: string[];
  sharedBillId: number | null;
}
export interface MergePreview {
  selected: MergeMember[];
  selectedCount: number;
  currency: string;
  amount: string;
  checks: { key: string; label: string; passed: boolean; detail: string }[];
  merge: Action;
  token: string;
  sourceBills: { id: number; blNo: string; fileName: string }[];
  sharedBillId: number;
  existingBillCount: number;
  existingContractCount: number;
  contracts: {
    key: string;
    contractNo: string;
    sellerName: string;
    declarationNos: string[];
    currency: string;
    amount: string;
  }[];
}
export interface ConfirmMerge extends MergeSelection {
  requestId: string;
  previewToken: string;
}
