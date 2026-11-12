import { http } from "../../shared/api/http";
import { readImportFile } from "../../shared/api/import-file";
import type { CustomsImportResult, CustomsReceiptList, CustomsReceiptQuery } from "./customs-types";

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

// ids 为空时重新匹配全部回执
export const rematchCustomsReceipts = (ids: number[] = []) =>
  http<{ rematched: number }>("/review/customs-receipts/rematch", "POST", { ids });
