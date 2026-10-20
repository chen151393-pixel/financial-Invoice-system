/**
 * NS 回写接口契约（计划中的 /api/writeback/*）。金额、状态文字、能否操作及原因全部来自后端，
 * 前端只展示，不计算金额或推断是否允许写入。
 */

export type WritebackPhase =
  | "ready"
  | "blocked"
  | "pending"
  | "executing"
  | "unknown"
  | "failed"
  | "succeeded";

export interface Allowed {
  allowed: boolean;
  reason: string;
}

export interface WriteSwitch {
  enabled: boolean;
  account: string;
  reason: string;
}

export interface WritebackItem {
  invoiceId: string;
  invoiceNo: string;
  invoiceDate: string;
  vendorName: string;
  amount: string;
  currency: string;
  purchaseOrders: string;
  allocation: string;
  phase: WritebackPhase;
  label: string;
  requestId: string | null;
  note: string | null;
  preview: Allowed;
}

export interface WritebackList {
  items: WritebackItem[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
  counts: Partial<Record<WritebackPhase | "all", number>>;
  write: WriteSwitch;
}

export interface WritebackQuery {
  phase: WritebackPhase | "";
  vendor: string;
  invoiceNo: string;
  dateFrom: string;
  dateTo: string;
  page: number;
  pageSize: number;
}

export interface PreviewLine {
  billNo: string;
  poNo: string;
  subPoNo: string;
  due: string;
  received: string;
  remaining: string;
  amount: string;
  receivedAfter: string;
  check: { passed: boolean; label: string };
}

export interface ResultBill {
  billNo: string;
  subPoNo: string;
  before: string;
  amount: string;
  after: string | null;
  status: string;
  passed: boolean;
}

export interface WritebackEvent {
  at: string;
  action: string;
  actor: string;
  detail: string;
}

export interface WritebackRequest {
  requestId: string;
  invoiceId: string;
  invoiceNo: string;
  invoiceDate: string;
  vendorName: string;
  vendorRef: string;
  invoiceAmount: string;
  totalAmount: string;
  currency: string;
  account: string;
  phase: Exclude<WritebackPhase, "ready" | "blocked">;
  label: string;
  message: string;
  createdAt: string;
  createdBy: string;
  expiresAt: string | null;
  readAt: string | null;
  checks: { label: string; passed: boolean; detail: string | null }[];
  lines: PreviewLine[];
  totalLabel: string;
  operations: string[];
  execute: Allowed;
  refresh: Allowed;
  verify: Allowed;
  records: { label: string; url: string | null }[];
  bills: ResultBill[];
  poll: boolean;
  events: WritebackEvent[];
}

export const PHASE_TABS: readonly {
  value: WritebackQuery["phase"];
  label: string;
  key: WritebackPhase | "all";
}[] = [
  { value: "", label: "全部", key: "all" },
  { value: "ready", label: "可回写", key: "ready" },
  { value: "pending", label: "待确认", key: "pending" },
  { value: "executing", label: "执行中", key: "executing" },
  { value: "unknown", label: "结果待核实", key: "unknown" },
  { value: "failed", label: "失败", key: "failed" },
  { value: "succeeded", label: "已回写", key: "succeeded" },
];

/** 后端返回 UTC ISO 时间，页面按北京时间展示；缺失时显示“—”，不显示虚构时间。 */
export function writebackTime(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}
