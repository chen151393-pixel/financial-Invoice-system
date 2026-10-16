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
    counts: { saved: number; failed: number; unknown: number; not_processed: number };
    items: {
      id: string;
      number: string;
      status: "saved" | "failed" | "unknown" | "not_processed";
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
export const pullRecords = (
  kind: SourceKind,
  offset: number,
  range: DateRange,
  save = false,
  progressId?: string,
) =>
  http<PullResult>(`/ns/sync/${kind}/${save ? "pull-save" : "pull"}`, "POST", {
    offset,
    limit: 20,
    requireDateRange: true,
    ...(save ? { partialSave: true } : {}),
    ...(progressId ? { progressId } : {}),
    ...range,
  });

export type SyncProgress = {
  state: "pending" | "running" | "completed" | "failed";
  label: string;
  completed: number | null;
  total: number | null;
  elapsedSeconds: number;
};
export const createProgress = () => http<{ progressId: string }>("/sync/ns/progress", "POST", {});
export const getProgress = (identity: string) => http<SyncProgress>(`/sync/ns/progress/${identity}`);
