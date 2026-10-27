import { http } from "../../../shared/api/http";
import type { InvoiceFileItem, InvoiceFileUpload } from "../types/invoice-file";

// 发票文件批量上传：只提交原文件与可选的人工指定发票号码，归属由后端按比对通过的分配确定。
export const uploadInvoiceFiles = (files: InvoiceFileUpload[]) =>
  http<{ items: InvoiceFileItem[] }>("/matching/invoice-files/upload", "POST", { files });
