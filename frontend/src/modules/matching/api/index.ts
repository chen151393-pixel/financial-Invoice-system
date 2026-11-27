import { http } from "../../../shared/api/http";
import type { InvoiceTotals, InvoiceTotalsFilters } from "../types/invoice-totals";
import type { ManualOrderBody, ManualOrderCandidates } from "../types/manual-order";
import type { OrderCandidates, OrderConfirmBody } from "../types/order-matching";
import type {
  ConfirmBody,
  InvoiceBatchResult,
  InvoiceMatchFilters,
  InvoiceMatchList,
  InvoiceMatching,
  InvoiceQueue,
  InvoiceQueueRow,
  QueueQuery,
} from "../types/matching";

export type { InvoiceMatchFilters, InvoiceMatchList, MatchStatus, MatchingSummary } from "../types/matching";
export type { InvoiceTotals } from "../types/invoice-totals";

const allocation = (id: string) => `/matching/allocations/${encodeURIComponent(id)}`;

export const getInvoiceMatching = (invoiceId: string, signal?: AbortSignal) =>
  http<InvoiceMatching>(`/matching/invoices/${encodeURIComponent(invoiceId)}`, "GET", undefined, signal);

export const findOrderCandidates = (body: { invoiceId: string; keyword: string; page: number }) =>
  http<OrderCandidates>("/matching/order-candidates/query", "POST", body);

export const confirmOrder = (body: OrderConfirmBody) =>
  http<InvoiceMatching>("/matching/orders/confirm", "POST", body);
// 日期为空时提交 null，由后端按"不限"处理
export const getMatchingQueue = (query: QueueQuery, signal?: AbortSignal) =>
  http<InvoiceQueue>(
    "/matching/invoice-queue/query",
    "POST",
    {
      ...query,
      invoiceFrom: query.invoiceFrom || null,
      invoiceTo: query.invoiceTo || null,
    },
    signal,
  );
// 进项发票列表按匹配状态筛选；日期为空时提交 null，由后端按“不限”处理
export const queryInvoiceMatchList = <List>(filters: InvoiceMatchFilters, signal?: AbortSignal) =>
  http<InvoiceMatchList<List>>(
    "/matching/invoices/query",
    "POST",
    {
      q: filters.q,
      invoice_no: filters.invoice_no,
      seller_name: filters.seller_name,
      seller_tax_no: filters.seller_tax_no,
      account: filters.account,
      status: filters.status,
      date_from: filters.date_from || null,
      date_to: filters.date_to || null,
      matchStatus: filters.matchStatus,
      page: filters.page,
      page_size: filters.pageSize,
    },
    signal,
  );
export function getInvoiceTotals(filters: InvoiceTotalsFilters, signal?: AbortSignal) {
  const params = new URLSearchParams();
  for (const key of [
    "q",
    "invoice_no",
    "seller_name",
    "seller_tax_no",
    "account",
    "status",
    "date_from",
    "date_to",
  ] as const)
    if (filters[key]) params.set(key, filters[key]);
  return http<InvoiceTotals>(`/matching/invoice-totals?${params}`, "GET", undefined, signal);
}
// 手动关联候选：一行一张整张子采购单
export const findManualOrders = (invoiceId: string, invoiceItemId: string, keyword: string) =>
  http<ManualOrderCandidates>("/matching/manual-orders/candidates/query", "POST", {
    invoiceId,
    invoiceItemId,
    keyword,
  });
// 发票行关联整张子采购单：各明细按填写的数量金额整组保存并通过，可选原子替换一条已确认关联
export const createManualOrder = (body: ManualOrderBody) =>
  http<InvoiceMatching>("/matching/manual-orders", "POST", body);

export const confirmAllocation = (id: string, body: ConfirmBody) =>
  http<InvoiceMatching>(`${allocation(id)}/confirm`, "POST", body);
export const rejectAllocation = (id: string, note: string) =>
  http<InvoiceMatching>(`${allocation(id)}/reject`, "POST", { note });
export const cancelAllocation = (id: string, reason: string) =>
  http<InvoiceMatching>(`${allocation(id)}/cancel`, "POST", { reason });
// 整单建议整组通过 / 驳回：发票行对应的一张或多张整张子采购单
export const confirmGroup = (
  groupId: string,
  invoiceId: string,
  invoiceVersionId: string | null,
  note: string,
) =>
  http<InvoiceMatching>(`/matching/groups/${encodeURIComponent(groupId)}/confirm`, "POST", {
    invoiceId,
    invoiceVersionId,
    note,
  });
export const rejectGroup = (groupId: string, invoiceId: string, note: string) =>
  http<InvoiceMatching>(`/matching/groups/${encodeURIComponent(groupId)}/reject`, "POST", {
    invoiceId,
    note,
  });
export const confirmBatch = (ids: string[]) =>
  http<{ confirmed: number; skipped: { id: string; reason: string }[] }>(
    "/matching/allocations/confirm-batch",
    "POST",
    { ids },
  );
export const confirmInvoiceBatch = (rows: InvoiceQueueRow[], note: string) =>
  http<InvoiceBatchResult>("/matching/invoice-queue/confirm-batch", "POST", {
    items: rows.map((row) => ({
      invoiceId: row.invoice.id,
      invoiceVersionId: row.invoice.versionId,
      allocationIds: row.batchIds,
    })),
    note,
  });
export const generateProposals = (invoiceIds: string[]) =>
  http<{ created: number }>("/matching/proposals/generate", "POST", { invoiceIds });

export const reverifyAllocation = (id: string, body: ConfirmBody) =>
  http<InvoiceMatching>(`${allocation(id)}/reverify`, "POST", body);
