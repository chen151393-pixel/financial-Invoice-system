import { http } from "../../../shared/api/http";
import type {
  ImportConfiguration,
  ImportFile,
  ImportResult,
  InvoiceDetail,
  InvoiceAccountOption,
  InvoiceStats,
} from "../types/invoice";

export const getInvoiceAccounts = () =>
  http<{ items: InvoiceAccountOption[] }>("/sync/lemon/invoices/accounts");
export const getInvoiceStats = (query: URLSearchParams) => http<InvoiceStats>(`/invoices/stats?${query}`);
export const getInvoice = (id: string) => http<InvoiceDetail>(`/invoices/${encodeURIComponent(id)}`);

export const getImportConfiguration = () => http<ImportConfiguration>("/invoices/import/configuration");
export const previewFile = (file: ImportFile) => http<ImportResult>("/invoices/import/preview", "POST", file);
export const confirmFile = (file: ImportFile, previewToken: string) =>
  http<ImportResult>("/invoices/import/confirm", "POST", { ...file, previewToken });

export { readImportFile } from "../../../shared/api/import-file";
