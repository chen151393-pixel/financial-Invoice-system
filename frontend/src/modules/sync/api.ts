import { http } from "../../shared/api/http";

export type SourceKind = "purchase-orders" | "sub-purchase-orders" | "customs-declarations";
export type Source = {
  kind: SourceKind;
  label: string;
  recordType: string;
  allowed: boolean;
  reason: string;
  storageAllowed: boolean;
  storageReason: string;
};
export type DateRange = { startDate: string; endDate: string };
export type Sources = { sources: Source[]; lemon: { allowed: boolean; reason: string } };
export type PullResult = {
  batch?: {
    status: "completed" | "partial" | "interrupted";
    canContinue: boolean;
    // skipped：未出库（缺真实报关单号或无子采购单）的报关单及其子采购，拉取时跳过、不入库
    counts: { saved: number; skipped?: number; failed: number; unknown: number; not_processed: number };
    items: {
      id: string;
      number: string;
      status: "saved" | "skipped" | "failed" | "unknown" | "not_processed";
      reason: string;
    }[];
  };
  label: string;
  count: number;
  offset: number;
  hasMore: boolean;
  nextOffset: number | null;
  pulledAt: string;
  message: string;
  storage?: {
    savedAt: string | null;
    purchase: { created: number; updated: number; linesCreated: number; linesUpdated: number };
    customs: { created: number; updated: number; linesCreated: number; linesUpdated: number };
    warnings?: string[];
    relations?: {
      declarations: number;
      collected: number;
      partial: number;
      rawLines: number;
      packingLines: number;
      purchaseLinks: number;
    };
  };
  dateRange: DateRange & { label: string };
  rows: { id: string; number: string; record: Record<string, unknown> }[];
};
export const getSources = () => http<Sources>("/ns/sync/sources");
/** 只读拉取一批，不入库；保存改用后台批次 startRun。 */
export const pullRecords = (kind: SourceKind, offset: number, range: DateRange) =>
  http<PullResult>(`/ns/sync/${kind}/pull`, "POST", {
    offset,
    limit: 20,
    requireDateRange: true,
    ...range,
  });

export type SyncProgress = {
  state: "pending" | "running" | "completed" | "failed";
  label: string;
  completed: number | null;
  total: number | null;
  elapsedSeconds: number;
};
export type SaveKind = Exclude<SourceKind, "purchase-orders">;
export type NsRun = {
  requestId: string;
  kind: SaveKind;
  request: DateRange & { offset: number; limit: number };
  status: "running" | "completed" | "partial" | "interrupted" | "failed" | "unknown";
  statusLabel: string;
  progress: SyncProgress | null;
  result: PullResult | null;
  error: string | null;
};
/** 提交后立即返回；同一请求编号重复提交只返回原记录，不会重新执行。 */
export const startRun = (kind: SaveKind, requestId: string, offset: number, range: DateRange) =>
  http<NsRun>("/sync/ns/runs", "POST", {
    requestId,
    kind,
    offset,
    limit: 20,
    requireDateRange: true,
    ...range,
  });
export const getRun = (requestId: string) => http<NsRun>(`/sync/ns/runs/${encodeURIComponent(requestId)}`);
