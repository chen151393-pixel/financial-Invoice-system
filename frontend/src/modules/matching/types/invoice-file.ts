// 与后端 matching/vo/invoice_file_vo.py 一致
export interface InvoiceFileUpload {
  filename: string;
  content: string;
  invoiceNo: string;
}
export interface InvoiceFileItem {
  filename: string;
  invoiceNumber: string;
  status: "saved" | "unmatched" | "ambiguous" | "not_ready" | "conflict" | "failed";
  reason: string;
  archivePaths: string[];
}

export const INVOICE_FILE_STATUS: Record<InvoiceFileItem["status"], string> = {
  saved: "已保存",
  unmatched: "未识别发票号码",
  ambiguous: "匹配多张发票",
  not_ready: "暂不能归档",
  conflict: "已有不同文件，未覆盖",
  failed: "未保存",
};
