import { http } from "../../../shared/api/http";
import type {
  Association,
  CatalogItem,
  CatalogPage,
  ImportReceipt,
  ImportResult,
  PreviewPage,
  SupplierOptions,
} from "../types/external-group";
export { readImportFile } from "../../../shared/api/import-file";
const root = "/tasks/external-groups";
export const previewGroups = (file: { filename: string; content: string }, account: string) =>
  http<ImportReceipt>(`${root}/import/preview`, "POST", { ...file, account });
export const getGroupPreview = (importId: string, page: number) =>
  http<PreviewPage>(`${root}/import/query`, "POST", { importId, page });
export const confirmGroups = (importId: string, selections: Record<number, Association>) =>
  http<ImportResult>(`${root}/import/confirm`, "POST", {
    importId,
    selections: Object.entries(selections).map(([rowNo, choice]) => ({
      rowNo: Number(rowNo),
      supplierId: choice.supplier.supplierId,
      revision: choice.supplier.binding?.revision ?? 0,
      replaceExisting: choice.replaceExisting,
    })),
  });
export const queryExternalGroups = (keyword: string, status: string, page: number) =>
  http<CatalogPage>(`${root}/query`, "POST", { keyword, status, page });
export const findSuppliers = (keyword: string, account: string, page: number) =>
  http<SupplierOptions>("/tasks/supplier-groups/suppliers/query", "POST", { keyword, account, page });
export const associateGroup = (group: CatalogItem, choice: Association) =>
  http(`${root}/associate`, "POST", {
    chatId: group.chatId,
    catalogRevision: group.revision,
    supplierId: choice.supplier.supplierId,
    revision: choice.supplier.binding?.revision ?? 0,
    replaceExisting: choice.replaceExisting,
  });
