import { http, HttpError } from "../../../shared/api/http";
import { openLocalSession } from "../../identity/api";
import type { InvoiceTotals, InvoiceTotalsFilters } from "../types/invoice-totals";
import type { OrderCandidates, OrderConfirmBody } from "../types/order-matching";
import type {
  Candidate,
  ConfirmBody,
  InvoiceMatchFilters,
  InvoiceMatchList,
  InvoiceMatching,
  ManualBody,
  InvoiceQueue,
  QueueQuery,
} from "../types/matching";

export type { InvoiceMatchFilters, InvoiceMatchList, MatchStatus, MatchingSummary } from "../types/matching";
export type { InvoiceTotals } from "../types/invoice-totals";

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

export const findOrderCandidates = (body: {
  invoiceId: string;
  keyword: string;
  page: number;
  conversionNumerator: string;
  conversionDenominator: string;
}) => read<OrderCandidates>("/matching/order-candidates/query", "POST", body);

export const confirmOrder = (body: OrderConfirmBody) =>
  http<InvoiceMatching>("/matching/orders/confirm", "POST", body);
// 日期为空时提交 null，由后端按"不限"处理
export const getMatchingQueue = (query: QueueQuery) =>
  read<InvoiceQueue>("/matching/invoice-queue/query", "POST", {
    ...query,
    invoiceFrom: query.invoiceFrom || null,
    invoiceTo: query.invoiceTo || null,
  });
// 进项发票列表按匹配状态筛选；日期为空时提交 null，由后端按“不限”处理
export const queryInvoiceMatchList = <List>(filters: InvoiceMatchFilters) =>
  read<InvoiceMatchList<List>>("/matching/invoices/query", "POST", {
    q: filters.q,
    account: filters.account,
    status: filters.status,
    date_from: filters.date_from || null,
    date_to: filters.date_to || null,
    matchStatus: filters.matchStatus,
    page: filters.page,
    page_size: filters.pageSize,
  });
export function getInvoiceTotals(filters: InvoiceTotalsFilters) {
  const params = new URLSearchParams();
  for (const key of ["q", "account", "status", "date_from", "date_to"] as const)
    if (filters[key]) params.set(key, filters[key]);
  return read<InvoiceTotals>(`/matching/invoice-totals?${params}`);
}
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
