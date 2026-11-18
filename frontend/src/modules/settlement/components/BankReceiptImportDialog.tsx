import { useState } from "react";
import { Alert, Button, Dialog, FileDropzone } from "../../../shared/components/ui";
import { importBankReceipts } from "../api";
import type { BankReceiptImportResult } from "../types";

export function BankReceiptImportDialog({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<BankReceiptImportResult | null>(null);

  async function upload() {
    if (!file || busy) return;
    setBusy(true);
    setError("");
    try {
      const imported = await importBankReceipts(file);
      setResult(imported);
      setFile(null);
      if (imported.imported > 0) onImported();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "导入失败，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title="导入银行流水" busy={busy} onClose={onClose}>
      <div className="settlement-detail">
        <FileDropzone
          label="选择或拖入银行流水"
          hint="支持单个 .xlsx 文件，大小不超过 4 MB。请填写「境外收货人名称」列。"
          accept=".xlsx"
          disabled={busy}
          onFiles={([selected]) => {
            setFile(selected ?? null);
            setResult(null);
            setError("");
          }}
        />
        {file && <p className="settlement-form__hint">{file.name}</p>}
        {error && (
          <Alert tone="danger" title="导入失败">
            {error}
          </Alert>
        )}
        {result && (
          <Alert tone="success" title="导入完成">
            新增 {result.imported} 笔，跳过重复 {result.duplicates} 笔，跳过非来账 {result.ignored} 笔。
          </Alert>
        )}
        <div className="settlement-form__actions">
          <Button variant="primary" disabled={!file || busy} onClick={() => void upload()}>
            {busy ? "正在导入…" : "确认导入"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
