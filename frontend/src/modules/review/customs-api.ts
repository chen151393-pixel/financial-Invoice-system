import { http } from "../../shared/api/http";
import { readImportFile } from "../../shared/api/import-file";
import type {
  CustomsApproveResult,
  CustomsImportResult,
  CustomsReceipt,
  CustomsReceiptList,
  CustomsReceiptQuery,
} from "./customs-types";

export const queryCustomsReceipts = (query: CustomsReceiptQuery, signal?: AbortSignal) =>
  http<CustomsReceiptList>(
    "/review/customs-receipts/query",
    "POST",
    { ...query, exportFrom: query.exportFrom || null, exportTo: query.exportTo || null },
    signal,
  );

// 只上传原文件；列识别、校验、换版与比对全部在后端完成。
export async function importCustomsReceipt(file: File) {
  const body = await readImportFile(file);
  return http<CustomsImportResult>("/review/customs-receipts/import", "POST", body);
}

export const approveCustomsReceipts = (items: CustomsReceipt[], note: string) =>
  http<CustomsApproveResult>("/review/customs-receipts/approve-batch", "POST", {
    items: items.map((item) => ({ id: item.id, token: item.approval.token })),
    method: "manual",
    note,
  });
