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
export interface TaskListQuery {
  keyword: string;
  account: string;
  supplierId: string;
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

export interface TaskDetail {
  task: TaskSummary;
  lines: TaskLine[];
  reasons: string[];
  sourceStatus: "current" | "superseded";
  sourceMessage: string;
  prepare: Capability;
  notify: Capability;
  compare: Capability;
  steps: { label: string; description: string; state: "done" | "current" | "waiting" }[];
  documents: TaskDocument[];
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
