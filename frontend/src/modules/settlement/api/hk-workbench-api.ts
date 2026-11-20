import { http } from "../../../shared/api/http";
import type { HkWorkbench, HkWorkbenchQuery, HkReceiptCheck } from "../types/hk-workbench";
export const queryHkWorkbench = (query: HkWorkbenchQuery, signal?: AbortSignal) =>
  http<HkWorkbench>("/settlement/hk-workbench/query", "POST", query, signal);

export const previewHkReceipt = (
  declarationNos: string[],
  receivedAmount: string,
  receivedFee: string,
  signal?: AbortSignal,
) =>
  http<HkReceiptCheck>(
    "/settlement/hk-workbench/preview",
    "POST",
    { declarationNos, receivedAmount, receivedFee },
    signal,
  );
export const exportHkWorkbench = (query: HkWorkbenchQuery) =>
  http<{ fileName: string; content: string }>("/settlement/hk-workbench/export", "POST", query);
