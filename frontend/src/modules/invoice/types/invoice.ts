// 与后端 invoice 模块 VO 一致；金额为十进制字符串，前端不重算。
export type InvoiceRow = {
  id: string;
  number: string;
  date: string | null;
  seller: string | null;
  sellerTaxNo: string | null;
  type: string | null;
  businessType: string | null;
  status: string;
  sourceStatus: "normal" | "red_offset" | "void" | "unknown";
  displayStatus: "normal" | "red_letter" | "red_offset" | "void" | "unknown";
  statusNotice: string | null;
  currency: string;
  net: string | null;
  tax: string | null;
  gross: string | null;
  lineCount: number;
  importedAt: string;
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
    currency: string;
    count: number;
    net: string | null;
    tax: string | null;
    gross: string | null;
  }[];
};
export type InvoiceLine = {
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
};
export type InvoiceDetail = InvoiceRow & {
  detailStatusLabel: string;
  invoiceCode: string | null;
  buyer: string | null;
  buyerTaxNo: string | null;
  remark: string | null;
  lines: InvoiceLine[];
};
export type InvoiceFilters = {
  q: string;
  account: string;
  status: string;
  date_from: string;
  date_to: string;
};
export type InvoiceAccountOption = { value: string; label: string };

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
  updated: number;
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
    action: "new" | "updated" | "unchanged" | "conflict";
  }[];
};
