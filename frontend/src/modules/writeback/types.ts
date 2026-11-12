export interface TaskSummary {
  id: string;
  taskNo: string;
  invoiceId: string;
  invoiceNo: string;
  vendorName: string;
  parentOrders: { id: string; number: string }[];
  amount: string;
  state: string;
  stateLabel: string;
  reason: string;
  revision: number;
  historical: boolean;
  updatedAt: string;
  writeback: { allowed: boolean; reason: string };
}
export interface TaskList {
  items: TaskSummary[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  counts: Record<"all" | WritebackGroup, number>;
  states: { state: string; label: string; group: WritebackGroup; count: number }[];
}
export type WritebackGroup = "pending" | "executing" | "applied" | "attention" | "stale";
export interface TaskQuery {
  keyword: string;
  taskNo: string;
  invoiceNo: string;
  supplierName: string;
  parentOrderNo: string;
  state: string;
  group: WritebackGroup | "";
  page: number;
  pageSize: number;
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
  // 后端按审核快照与查询结果补的业务名称；取不到时为空串，页面不展示内部 ID
  purchaseOrderNo: string;
  subPurchaseOrderNo: string;
  subsidiaryName: string;
  currency: string;
  availableInvoiceAmount: string;
  issues: string[];
}
export interface SourceOrder {
  subPurchaseOrderId: string;
  orderNo: string;
  parentOrderNo: string;
  parentOrderId: string;
  amount: string;
  lineCount: number;
  eligibleBillIds: string[];
  allocations: { allocationId: string; purchaseLineId: string; amount: string }[];
}
export interface OrderTarget {
  subPurchaseOrderId: string;
  billId: string;
}
export interface TargetLine {
  allocationId: string;
  billId: string;
  amount: string;
}
export interface Plan {
  allocations: TargetLine[];
  orders: (OrderTarget & { orderNo: string; billNumber: string; amount: string })[];
  evidence: string;
  confirmedBy: string;
  // 确认人的飞书人员姓名，由后端按操作者标识查得；查不到时为原标识
  confirmedByName?: string;
  confirmedAt: string;
}
export interface TaskDetail extends TaskSummary {
  allocations: SourceAllocation[];
  orders: SourceOrder[];
  candidates: {
    queryId: string;
    readCompletedAt: string;
    registrationCheck?: {
      invoiceNumber: string;
      records: { id: string; number: string; date: string }[];
    } | null;
    purchaseOrders: { id: string; number?: string; reason: string; bills: Bill[] }[];
  } | null;
  plan: Plan | null;
  request: WriteRequest | null;
  actions: {
    refresh: boolean;
    confirm: boolean;
    confirmPreview: boolean;
    execute: boolean;
    // 账单补写：部分写入且已建 NS 发票记录、写入开关与白名单满足时可用
    repair?: boolean;
    resolve: boolean;
    markNotWritten: boolean;
  };
  repair?: { allowed: boolean; reason: string };
  querying: boolean;
  // actorName：操作者的飞书人员姓名（system 为“系统”）；查不到时为原标识
  audit: {
    action: string;
    actor: string;
    actorName?: string;
    detail: { reason?: string; evidence?: string };
    at: string;
  }[];
}
export interface PreviewLine {
  billId: string;
  billNumber: string;
  purchaseOrderId: string;
  purchaseOrderNo: string;
  before: string;
  amount: string;
  after: string;
  available: string;
  detailsTotal: string;
  difference: string;
  consistent: boolean;
}
export interface WriteRequest {
  requestId: string;
  state: string;
  invoice: { number: string; date: string; amount: string };
  preview: PreviewLine[];
  needsConfirmation: boolean;
  confirmedBy: string | null;
  confirmedByName?: string;
  confirmedAt: string | null;
  nsRecordId: string | null;
  sentAt: string | null;
  finishedAt: string | null;
}
export interface ResolveBody {
  revision: number;
  outcome: "applied" | "not_written";
  evidence: string;
  nsRecordId: string | null;
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
  orders: OrderTarget[];
}
