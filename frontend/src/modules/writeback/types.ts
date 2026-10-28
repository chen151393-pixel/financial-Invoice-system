export interface TaskSummary {
  id: string;
  taskNo: string;
  invoiceId: string;
  invoiceNo: string;
  vendorName: string;
  amount: string;
  state: string;
  stateLabel: string;
  reason: string;
  revision: number;
  historical: boolean;
  updatedAt: string;
  writeback: { allowed: false; reason: string };
}
export interface TaskList {
  items: TaskSummary[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}
export interface SourceAllocation {
  allocationId: string;
  orderNo: string;
  parentOrderNo: string;
  parentOrderId: string;
  amount: string;
}
export interface Bill {
  billId: string;
  billNumber: string;
  purchaseOrderId: string;
  subPurchaseOrderId: string;
  subsidiaryId: string;
  currency: string;
  availableInvoiceAmount: string;
  issues: string[];
}
export interface TargetLine {
  allocationId: string;
  billId: string;
  amount: string;
}
export interface Plan {
  allocations: TargetLine[];
  evidence: string;
  confirmedBy: string;
  confirmedAt: string;
}
export interface TaskDetail extends TaskSummary {
  allocations: SourceAllocation[];
  candidates: {
    queryId: string;
    readCompletedAt: string;
    purchaseOrders: { id: string; number?: string; reason: string; bills: Bill[] }[];
  } | null;
  plan: Plan | null;
  actions: { refresh: boolean; confirm: boolean };
  querying: boolean;
  audit: { action: string; actor: string; detail: { reason?: string; evidence?: string }; at: string }[];
}
export interface InvoiceReadiness {
  ready: boolean;
  reason: string;
  task: TaskSummary | null;
}
export interface ConfirmBody {
  revision: number;
  requestId: string;
  confirmScope: true;
  evidence: string;
  allocations: TargetLine[];
}
