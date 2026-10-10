import { http, HttpError } from "../../shared/api/http";
import { openLocalSession } from "../identity/api";
import type { InvoiceDetail } from "../invoice/api";
export type MatchingPreview = {
  invoice: InvoiceDetail;
  purchaseCount: number;
  purchaseLineCount: number;
  sameSupplierCount: number;
  candidateCount: number;
  fieldMatchCount: number;
  truncated: boolean;
  allowed: boolean;
  reason: string;
  priceReason: string;
  snapshot: string;
  remarkOrderCount: number;
  linkAllowed?: boolean;
  linkReason?: string;
  manualLinkAllowed: boolean;
  manualLinkReason: string;
  page: number;
  hasNext: boolean;
  links?: {
    invoiceLineId: string;
    purchaseLineId: string;
    orderNo: string | null;
    needsReview: boolean;
    manualConfirmation: boolean;
    manualReason: string;
    warnings: string[];
  }[];
  allocations: {
    invoiceLineId: string;
    purchaseLineId: string;
    quantity: string;
    gross: string;
    needsReview: boolean;
    orderNo: string | null;
  }[];
  candidates: {
    invoiceLineId: string;
    invoiceItem: string | null;
    purchaseLineId: string;
    orderNo: string;
    parentOrderNo: string | null;
    customsNo: string | null;
    declarationNo: string | null;
    supplier: string | null;
    item: string | null;
    declarationName: string | null;
    unit: string | null;
    quantity: string | null;
    price: string | null;
    gross: string | null;
    currency: string | null;
    allFieldsMatched: boolean;
    basis: string;
    matchStatus: string;
    calculatedInvoicePrice: string | null;
    allowed: boolean;
    reason: string;
    invoiceRemaining: string;
    purchaseRemaining: string;
    suggestedQuantity: string;
    checks: {
      label: string;
      matched: boolean;
      invoiceValue: string | null;
      purchaseValue: string | null;
      difference: string | null;
    }[];
    warnings: string[];
  }[];
};
export const previewMatching = async (id: string, query?: URLSearchParams) => {
  const result = await readMatching<MatchingPreview>(
    `/matching/invoices/${encodeURIComponent(id)}${query ? `?${query}` : ""}`,
  );
  if (typeof result.manualLinkAllowed !== "boolean") {
    throw new Error("匹配接口尚未更新，请重启后端服务后重试");
  }
  return result;
};

export type MatchingCandidate = MatchingPreview["candidates"][number];
export type MatchingSummary = {
  invoiceId: string;
  method: string;
  confidence: string;
  validation: string;
  tone: "neutral" | "success" | "warning";
};
export const getMatchingSummaries = (invoiceIds: string[]) =>
  readMatching<{ rows: MatchingSummary[] }>("/matching/summaries", "POST", { invoiceIds });

export type LinkReview = {
  allowed: boolean;
  reason: string;
  warnings: string[];
  requiresManualConfirmation: boolean;
};

export type ConfirmMatching = {
  requestId: string;
  snapshot: string;
  invoiceLineId: string;
  purchaseLineId: string;
  quantity: string;
};
export const confirmMatching = (id: string, body: ConfirmMatching) =>
  http<{ message: string; quantity: string; gross: string }>(
    `/matching/invoices/${encodeURIComponent(id)}/confirm`,
    "POST",
    body,
  );

export type LinkMatching = {
  requestId: string;
  snapshot: string;
  pairs: { invoiceLineId: string; purchaseLineId: string }[];
  manualConfirmation?: boolean;
  manualReason?: string;
};
export const reviewMatchingLinks = (id: string, body: Pick<LinkMatching, "snapshot" | "pairs">) =>
  readMatching<LinkReview>(`/matching/invoices/${encodeURIComponent(id)}/links/review`, "POST", body);
export const linkMatching = (id: string, body: LinkMatching) =>
  http<{ message: string; linkedLines: number }>(
    `/matching/invoices/${encodeURIComponent(id)}/links`,
    "POST",
    body,
  );

// 搜索和复核不写数据，允许会话失效后恢复一次；保存接口不自动重试。
async function readMatching<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  try {
    return await http<T>(path, method, body);
  } catch (error) {
    if (!(error instanceof HttpError) || error.status !== 401) throw error;
    await openLocalSession();
    return http<T>(path, method, body);
  }
}
