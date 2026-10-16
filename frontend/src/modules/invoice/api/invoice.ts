import { http } from "../../../shared/api/http";
import type {
  ImportConfiguration,
  ImportFile,
  ImportResult,
  InvoiceDetail,
  InvoiceListResult,
} from "../types/invoice";

export const listInvoices = (query: URLSearchParams) => http<InvoiceListResult>(`/invoices?${query}`);
export const getInvoice = (id: string) => http<InvoiceDetail>(`/invoices/${encodeURIComponent(id)}`);

export const getImportConfiguration = () => http<ImportConfiguration>("/invoices/import/configuration");
export const previewFile = (file: ImportFile) => http<ImportResult>("/invoices/import/preview", "POST", file);
export const confirmFile = (file: ImportFile, previewToken: string) =>
  http<ImportResult>("/invoices/import/confirm", "POST", { ...file, previewToken });

export { readImportFile } from "../../../shared/api/import-file";
