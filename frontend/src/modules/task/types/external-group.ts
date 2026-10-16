import type { GroupFields, SupplierOption } from "./supplier-group";
export interface ExternalGroup extends GroupFields {
  memberCount: number | null;
  department: string;
  createdAt: string;
}
export interface Candidate extends SupplierOption {
  reason?: string;
}
export interface PreviewRow {
  rowNo: number;
  groupName: string;
  group: ExternalGroup | null;
  issue: string;
  catalogRevision: number;
  candidates: Candidate[];
  candidateCount: number;
}
export interface ImportReceipt {
  importId: string;
  filename: string;
  total: number;
  valid: number;
  invalid: number;
  matched: number;
  unmatched: number;
  status: string;
  confirm: { allowed: boolean; reason: string };
}
export interface PreviewPage extends ImportReceipt {
  suggestions: (Association & { rowNo: number })[];
  items: PreviewRow[];
  page: number;
  pageSize: number;
  pages: number;
}
export interface CatalogItem extends ExternalGroup {
  revision: number;
  filename: string;
  updatedAt: string;
  suppliers: SupplierOption[];
}
export interface CatalogPage {
  items: CatalogItem[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  manage: { allowed: boolean; reason: string };
}
export interface Association {
  supplier: SupplierOption;
  replaceExisting: boolean;
}
export interface ImportResult {
  importId: string;
  imported: number;
  bound: number;
  skipped: number;
  message: string;
}
export interface SupplierOptions {
  items: SupplierOption[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}
