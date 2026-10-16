import { http, HttpError } from "../../../shared/api/http";
import { openLocalSession } from "../../identity/api";
import type {
  Candidate,
  ConfirmBody,
  InvoiceMatching,
  ManualBody,
  MatchingSummary,
  Queue,
  QueueQuery,
} from "../types/matching";

export type { MatchingSummary } from "../types/matching";

const allocation = (id: string) => `/matching/allocations/${encodeURIComponent(id)}`;

// 只读查询允许会话失效后恢复一次；写操作不自动重试，结果不明时由用户刷新核实。
async function read<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  try {
    return await http<T>(path, method, body);
  } catch (error) {
    if (!(error instanceof HttpError) || error.status !== 401) throw error;
    await openLocalSession();
    return http<T>(path, method, body);
  }
}

export const getInvoiceMatching = (invoiceId: string) =>
  read<InvoiceMatching>(`/matching/invoices/${encodeURIComponent(invoiceId)}`);
export const getMatchingQueue = (query: QueueQuery) => read<Queue>("/matching/queue", "POST", query);
export const getMatchingSummaries = (invoiceIds: string[]) =>
  read<{ rows: MatchingSummary[] }>("/matching/summaries", "POST", { invoiceIds });
export const findCandidates = (invoiceId: string, invoiceItemId: string, keyword: string) =>
  read<{ rows: Candidate[]; total: number }>("/matching/candidates/query", "POST", {
    invoiceId,
    invoiceItemId,
    keyword,
  });

export const confirmAllocation = (id: string, body: ConfirmBody) =>
  http<InvoiceMatching>(`${allocation(id)}/confirm`, "POST", body);
export const rejectAllocation = (id: string, note: string) =>
  http<InvoiceMatching>(`${allocation(id)}/reject`, "POST", { note });
export const cancelAllocation = (id: string, reason: string) =>
  http<InvoiceMatching>(`${allocation(id)}/cancel`, "POST", { reason });
export const createAllocation = (body: ManualBody) =>
  http<InvoiceMatching>("/matching/allocations", "POST", body);
export const confirmBatch = (ids: string[]) =>
  http<{ confirmed: number; skipped: { id: string; reason: string }[] }>(
    "/matching/allocations/confirm-batch",
    "POST",
    { ids },
  );
export const generateProposals = (invoiceIds: string[]) =>
  http<{ created: number }>("/matching/proposals/generate", "POST", { invoiceIds });

export const reverifyAllocation = (id: string, body: ConfirmBody) =>
  http<InvoiceMatching>(`${allocation(id)}/reverify`, "POST", body);

export const replaceAllocation = (id: string, body: ManualBody, reason: string) =>
  http<InvoiceMatching>(`${allocation(id)}/replace`, "POST", { ...body, reason });
