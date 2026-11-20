import type { Action, DirectDocumentRow } from "../types";

export interface DocumentGroup {
  id: number;
  kind: "single" | "multiple";
  merge: Action;
  package: Action;
  packageUrl: string;
  groupNo: string;
  consignee: string;
  currency: string;
  amount: string;
  members: (Pick<
    DirectDocumentRow,
    "declarationNo" | "recordNo" | "consignee" | "exportCompany" | "currency" | "amount" | "salesOrders"
  > & { exportDate?: string })[];
  status: string;
  statusLabel: string;
  edit: Action;
  updateSource: Action;
  createdBy: string;
  createdAt: string;
}
export interface DocumentGroupList {
  items: DocumentGroup[];
  total: number;
  page: number;
  pageSize: number;
}

export interface GroupBasisPreview {
  groupId: number;
  oldConsignee: string;
  oldCurrency: string;
  newConsignee: string;
  newCurrency: string;
  declarationCount: number;
  amount: string;
  token: string;
  update: Action;
}
