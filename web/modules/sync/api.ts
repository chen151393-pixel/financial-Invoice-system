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
  label: string;
  count: number;
  offset: number;
  hasMore: boolean;
  nextOffset: number | null;
  pulledAt: string;
  message: string;
  storage?: {
    savedAt: string;
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
export const pullRecords = (kind: SourceKind, offset: number, range: DateRange, save = false) =>
  http<PullResult>(`/ns/sync/${kind}/${save ? "pull-save" : "pull"}`, "POST", {
    offset,
    limit: 20,
    ...range,
  });
