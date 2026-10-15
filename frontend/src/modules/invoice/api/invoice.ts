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

export function readImportFile(file: File): Promise<ImportFile> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("文件读取失败，请重新选择"));
    reader.onload = () => {
      if (typeof reader.result !== "string") return reject(new Error("文件读取失败"));
      resolve({ filename: file.name, content: reader.result.slice(reader.result.indexOf(",") + 1) });
    };
    reader.readAsDataURL(file);
  });
}
