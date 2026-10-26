// 与后端 task 模块 VO 一致；金额、数量为十进制字符串，前端不重算。
export interface Capability {
  allowed: boolean;
  reason: string;
}

export type TaskStatus =
  | "documents_pending"
  | "notify_pending"
  | "awaiting_invoice"
  | "partially_received"
  | "documents_incomplete"
  | "completed"
  | "superseded";

export interface TaskSummary {
  id: string;
  account: string;
  recordNumber: string;
  supplier: string;
  company: string;
  currency: string;
  status: TaskStatus;
  statusLabel: string;
  stage?: string;
  stageLabel?: string;
  reason: string;
  createdAt: string;
  reviewRevision: number;
  predecessorTaskIds: string[];
  orderNumbers: string[];
  lineCount: number;
  expectedAmount: string | null;
  // 兼容尚未更新的任务查询服务；缺失字段只展示待获取，不在前端补算。
  outstandingAmount?: string | null;
  receiptPercent?: string | null;
  receiptBarPercent?: string | null;
  followupEmployee?: string;
  lastContactAt?: string | null;
  waitingLabel?: string;
}
// 六个流程节点；key 与详情页分区、采购任务台的节点一致
export type TaskStepKey = "review" | "documents" | "notification" | "invoices" | "comparison" | "completion";
export interface TaskStep {
  key: TaskStepKey;
  label: string;
  description: string;
  state: "done" | "current" | "waiting";
}
export interface TaskCounts {
  tasks: number;
  awaitingInvoice: number;
  completed: number;
  needsAttention: number;
}
export interface TaskGroup {
  id: string;
  label: string;
  account: string;
  counts: TaskCounts;
  tasks: TaskSummary[];
}
// 业务状态（按报关单下最慢的任务归类）；空为不限
export type TaskStage = "" | "notify" | "invoicing" | "documents" | "completed";
export const stageLabels: Record<Exclude<TaskStage, "">, string> = {
  notify: "待通知开票",
  invoicing: "待核票",
  documents: "资料已回",
  completed: "开票完成",
};
// 上线只同步 NS 正式环境，列表不再按 NS 环境筛选（后端参数保留为可选）
export interface TaskListQuery {
  keyword: string;
  supplierId: string;
  stage: TaskStage;
  // 报关单创建日期（YYYY-MM-DD），须同时填写
  createdFrom: string;
  createdTo: string;
  groupBy: "supplier" | "declaration";
  status: "current" | "superseded" | "all";
  page: number;
  pageSize: number;
}
export interface TaskList {
  groupBy: TaskListQuery["groupBy"];
  groups: TaskGroup[];
  counts: TaskCounts;
  accounts: string[];
  // 供应商筛选选项由后端按当前任务返回
  suppliers: { id: string; name: string }[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}

export interface TaskLine {
  purchaseBasisId: string | null;
  ledgerSha256: string | null;
  requiresReview: boolean;
  pendingQuantity: string;
  pendingAmount: string;
  close: Capability;
  id: string;
  order: string;
  name: string;
  specification: string;
  quantity: string;
  unit: string;
  amount: string;
  currency: string;
  receivedQuantity: string;
  receivedAmount: string;
  status: "open" | "partial" | "received" | "superseded";
  statusLabel: string;
}

export interface TaskDocument {
  orderId: string;
  orderNumber: string;
  status: "pending" | "failed" | "ready";
  environment: string;
  nsId: string;
  filename: string;
  sha256: string;
  downloadedAt: string | null;
  archivePath: string | null;
  archivedAt: string | null;
  error: string;
  prepare: Capability;
}

export interface TaskEvent {
  at: string;
  actor: string;
  label: string;
  reason: string;
}

// 报关资料：报关单、销售合同、发票按报关单各一份，由 NS 下载；每类可单独重试。
export type DeclarationDocumentType = "customs_declaration" | "sales_contract" | "invoice";
export interface DeclarationDocument {
  type: DeclarationDocumentType;
  label: string;
  status: "unregistered" | "pending" | "archived" | "failed";
  statusLabel: string;
  files: { filename: string; path: string }[];
  error: string;
  attempts: number;
  archivedAt: string | null;
  retry: Capability;
}
export interface SignedContract {
  orderId: string;
  orderNumber: string;
  uploaded: boolean;
  filename: string;
  archivePath: string | null;
  uploadedAt: string | null;
  uploadedBy: string;
}
// 资料齐全情况由后端判断；子采购合同、报关单、销售合同、发票、回签合同全部到齐才算齐全。
export interface TaskCompletion {
  ready: boolean;
  missing: string[];
  reason: string;
}
export interface SignedUploadFile {
  filename: string;
  content: string;
  orderNo: string;
}
export interface SignedUploadItem {
  filename: string;
  orderNumber: string;
  status: "saved" | "unmatched" | "ambiguous" | "conflict" | "failed";
  reason: string;
  archivePath: string | null;
}

export interface TaskDetail {
  task: TaskSummary;
  lines: TaskLine[];
  reasons: string[];
  sourceStatus: "current" | "superseded";
  sourceMessage: string;
  prepare: Capability;
  notify: Capability;
  compare: Capability;
  steps: TaskStep[];
  documents: TaskDocument[];
  declarationDocuments: DeclarationDocument[];
  signedContracts: SignedContract[];
  completion: TaskCompletion | null;
  downloadEnvironment: string;
  notification: TaskNotification;
  events: TaskEvent[];
}

export interface NotificationDraft {
  revision: number;
  groupName: string;
  employee: string;
  message: string;
}
export interface NotificationRecord {
  revision: number;
  sentAt: string;
  note: string;
  confirmed: boolean;
}
export interface NotificationEvent {
  channel: string;
  revision: number;
  actor: string;
  at: string;
  groupName: string;
  employee: string;
  message: string;
  sentAt: string | null;
  recordedBy: string;
  note: string;
  attachments: string[];
}
export interface TaskNotification extends NotificationDraft {
  supplierGroup: {
    groupName: string;
    chatId: string;
    employee: string;
    userid: string;
    revision: number;
  } | null;
  groupConfigReason: string;
  defaultMessage: string;
  statusLabel: string;
  edit: Capability;
  record: Capability;
  send: Capability;
  history: NotificationEvent[];
}

export type ClosureRequest = {
  requestId: string;
  purchaseBasisId: string;
  ledgerSha256: string;
  reason: string;
};
