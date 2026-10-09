export interface InvoiceTask {
  id: string;
  account: string;
  recordNumber: string;
  supplier: string;
  company: string;
  currency: string;
  status: "documents_pending" | "notify_pending" | "awaiting_invoice" | "superseded";
  statusLabel: string;
  reason: string;
  createdAt: string;
  reviewRevision: number;
  snapshotId: string;
  orderNumbers: string[];
  lineCount: number;
  expectedAmount: string | null;
}
export interface TaskCounts {
  tasks: number;
  awaitingInvoice: number;
  receivedInvoices: number | null;
  needsAttention: number;
}
export interface InvoiceTaskGroup {
  id: string;
  label: string;
  account: string;
  counts: TaskCounts;
  tasks: InvoiceTask[];
}
export interface InvoiceTaskQuery {
  keyword: string;
  account: string;
  groupBy: "supplier" | "declaration";
  status: "current" | "superseded" | "all";
  page: number;
  pageSize: number;
}
export interface InvoiceTaskList {
  groupBy: InvoiceTaskQuery["groupBy"];
  groups: InvoiceTaskGroup[];
  counts: TaskCounts;
  accounts: string[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
}
export interface InvoiceTaskDetail {
  task: InvoiceTask;
  notification: TaskNotification;
  downloadEnvironment: string;
  documents: TaskDocument[];
  lines: {
    id: string;
    order: string;
    name: string;
    quantity: string;
    unit: string;
    amount: string;
    currency: string;
  }[];
  reasons: string[];
  sourceStatus: "current" | "changed" | "unavailable" | "superseded";
  sourceMessage: string;
  prepare: { allowed: boolean; reason: string };
  notify: { allowed: boolean; reason: string };
  compare: { allowed: boolean; reason: string };
  steps: { label: string; description: string; state: "done" | "current" | "waiting" }[];
}

export interface TaskDocument {
  orderId: string;
  orderNumber: string;
  status: "pending" | "archive_pending" | "ready";
  environment: string;
  nsId: string;
  filename: string;
  sha256: string;
  downloadedAt: string | null;
  archivePath: string | null;
  archivedAt: string | null;
  prepare: { allowed: boolean; reason: string };
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
  revision: number;
  actor: string;
  at: string;
  groupName: string;
  employee: string;
  message: string;
  sentAt: string | null;
  note: string;
  attachments: string[];
}
export interface TaskNotification extends NotificationDraft {
  defaultMessage: string;
  statusLabel: string;
  edit: { allowed: boolean; reason: string };
  record: { allowed: boolean; reason: string };
  send: { allowed: boolean; reason: string };
  history: NotificationEvent[];
}
