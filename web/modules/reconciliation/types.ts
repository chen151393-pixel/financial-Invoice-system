export interface PlSearchCriteria {
  type: "pl" | "customsRecord" | "declaration";
  pl: string;
  month: string;
  createdFrom: string;
  createdTo: string;
  showIncomplete: boolean;
}
export type ReviewStatus = "pending" | "approved" | "blocked";
export type ReviewFilter = "all" | ReviewStatus;
export interface PurchaseLine {
  id: string;
  name: string;
  model: string;
  parent: string;
  child: string;
  supplier: string;
  quantity: string;
  unit: string;
  price: string;
  amount: string;
  currency: string;
  note: string;
  scope?: "declared" | "order";
}
export interface CustomsLine {
  id: string;
  lineNo: number;
  name: string;
  model: string;
  quantity: string;
  unit: string;
  price: string;
  amount: string;
  currency: string;
  purchaseCount: number;
  purchaseLines: PurchaseLine[];
}
export interface ComparisonGroup {
  id: string;
  invoiceTaskCount?: number | null;
  snapshotId: string;
  account?: string;
  recordNumber: string;
  declaration: string;
  pl: string;
  company: string;
  customsCount: number;
  purchaseCount: number;
  customsLines: CustomsLine[];
  unlinkedLines: PurchaseLine[];
  warnings: string[];
  review: {
    status: ReviewStatus;
    label: string;
    allowed: boolean;
    reason: string;
    reviewedAt: string | null;
    reviewedBy: string | null;
    note: string;
  };
}
export interface ComparisonResult {
  source: "netsuite" | "database";
  requestId: string;
  readCompletedAt: string;
  groups: ComparisonGroup[];
  counts: Record<ReviewFilter | "customs" | "purchase" | "shown", number>;
  notices: string[];
  accounts?: string[];
  page?: number;
  pageSize?: number;
  total?: number;
  pages?: number;
}
export interface DeclarationListQuery {
  keyword: string;
  account: string;
  status: ReviewFilter;
  page: number;
  pageSize: number;
}
export type ComparisonState =
  | { kind: "ready"; result: ComparisonResult }
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string };
