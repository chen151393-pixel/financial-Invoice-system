import { http } from "../../../shared/api/http";

export type DetailAction = { invoiceId: string; allowed: boolean; reason: string };
export type DetailRun = {
  requestId: string;
  status: "running" | "completed" | "failed";
  error: string | null;
  result: null | {
    invoiceIds?: string[];
    message: string;
    completeDetails: number;
    pendingDetails: number;
    detailIssueCount?: number;
    detailIssues?: { number: string; reason: string }[];
  };
};
export const getDetailActions = (invoiceIds: string[]) =>
  http<{ rows: DetailAction[]; latest: DetailRun | null }>("/sync/lemon/invoices/detail-actions", "POST", {
    invoiceIds,
  });
export const refreshInvoiceDetails = (invoiceIds: string[], requestId: string) =>
  http<DetailRun>("/sync/lemon/invoices/refresh-details", "POST", { invoiceIds, requestId });
export const getDetailRun = (requestId: string) =>
  http<DetailRun>(`/sync/lemon/runs/${encodeURIComponent(requestId)}`);
