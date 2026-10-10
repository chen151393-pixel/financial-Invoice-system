import { http } from "../../shared/api/http";

export type InvoiceRow = {
  id: string;
  number: string | null;
  date: string | null;
  seller: string | null;
  sellerTaxNo: string | null;
  type: string | null;
  businessType: string | null;
  status: string;
  validation: string;
  currency: string | null;
  net: string | null;
  tax: string | null;
  gross: string | null;
  lineCount: number;
  importedAt: string | null;
  source: string;
};
export type InvoiceListResult = {
  total: number;
  page: number;
  pageSize: number;
  hasPrevious: boolean;
  hasNext: boolean;
  rows: InvoiceRow[];
  amounts: {
    currency: string | null;
    count: number;
    net: string | null;
    tax: string | null;
    gross: string | null;
  }[];
};
export type InvoiceDetail = InvoiceRow & {
  buyer: string | null;
  buyerTaxNo: string | null;
  remark: string | null;
  project: string | null;
  department: string | null;
  employee: string | null;
  voucher: string | null;
  invoiceCode: string | null;
  validationMessages: string[];
  lines: {
    id: string;
    number: string | null;
    item: string | null;
    specification: string | null;
    unit: string | null;
    quantity: string | null;
    unitPrice: string | null;
    net: string | null;
    taxRate: string | null;
    tax: string | null;
    gross: string | null;
  }[];
};
export const listInvoices = (query: URLSearchParams) => http<InvoiceListResult>(`/invoices?${query}`);
export const getInvoice = (id: string) => http<InvoiceDetail>(`/invoices/${encodeURIComponent(id)}`);

export type ImportFile = { filename: string; content: string };
export type ImportConfiguration = { allowed: boolean; reason: string; maxBytes: number };
export type ImportResult = {
  filename: string;
  invoiceCount: number;
  sourceInvoiceCount: number;
  excludedCount: number;
  businessType: string;
  lineCount: number;
  created: number;
  unchanged: number;
  conflicts: number;
  amount: string;
  saved: boolean;
  allowed: boolean;
  reason: string;
  previewToken: string | null;
  message: string;
  warnings: string[];
  rows: {
    number: string;
    date: string;
    seller: string;
    businessType: string;
    status: string;
    amount: string;
    lineCount: number;
    action: "new" | "unchanged" | "conflict";
  }[];
};
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
