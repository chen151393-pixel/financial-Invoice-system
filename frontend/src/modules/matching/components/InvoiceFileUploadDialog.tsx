import { readImportFile } from "../../../shared/api/import-file";
import { BatchUpload, type BatchUploadFile } from "../../../shared/components/ui";
import { INVOICE_FILE_STATUS, type InvoiceFileItem, type InvoiceFileUpload } from "../types/invoice-file";

/** 发票文件批量上传窗口：只读取文件并提交，归属、格式与覆盖规则以后端结果为准。 */
export function InvoiceFileUploadDialog({
  upload,
  onClose,
}: {
  upload: (files: InvoiceFileUpload[]) => Promise<{ items: InvoiceFileItem[] }>;
  onClose: (changed: boolean) => void;
}) {
  async function send(files: BatchUploadFile[]) {
    const body = await Promise.all(
      files.map(async ({ file, target }) => ({ ...(await readImportFile(file)), invoiceNo: target })),
    );
    return (await upload(body)).items.map((item) => ({
      filename: item.filename,
      target: item.invoiceNumber,
      status: item.status,
      reason: item.reason,
      paths: item.archivePaths,
    }));
  }

  return (
    <BatchUpload
      title="批量上传发票文件"
      help="支持 PDF、JPG、PNG，单个文件不超过 10 MB。文件名需包含发票号码（税务平台下载的文件名已包含），只归档比对已通过的发票：系统按其分配的子采购单保存到“月份/CD号_真实报关单号”文件夹，跨报关单时每个文件夹各存一份；已有不同文件时不会覆盖。"
      accept=".pdf,.jpg,.jpeg,.png"
      targetLabel="发票号码"
      targetMaxLength={100}
      statusLabels={INVOICE_FILE_STATUS}
      assignable={["unmatched", "ambiguous"]}
      upload={send}
      onClose={onClose}
    />
  );
}
