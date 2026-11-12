import { useRef, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  DataTable,
  Dialog,
  FileDropzone,
  type Tone,
} from "../../../shared/components/ui";
import { importCustomsReceipt } from "../customs-api";
import type { CustomsImportResult, ImportedDeclaration } from "../customs-types";

type FileOutcome =
  | { name: string; kind: "done"; result: CustomsImportResult }
  | { name: string; kind: "failed"; message: string };

const ACCEPT = ".xlsx,.xls,.csv";
const consistent = (status: ImportedDeclaration["status"]) =>
  status === "matched" || status === "split_matched";
const CONSIGNEE_TONE: Record<ImportedDeclaration["consignee"]["state"], Tone> = {
  saved: "success",
  empty: "neutral",
  pending: "info",
};

/**
 * 导入海关回执：逐个文件上传原文件，展示后端返回的列识别与逐张报关单结果。
 * 一个文件内任一行有误时后端整份拒绝，其余文件照常处理；关闭后由页面重新读取列表。
 */
export function CustomsImportDialog({ onClose }: { onClose: (changed: boolean) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [outcomes, setOutcomes] = useState<FileOutcome[]>([]);
  const [busy, setBusy] = useState(false);
  const changed = useRef(false);
  const sending = useRef(false);

  async function upload() {
    if (sending.current || !files.length) return;
    sending.current = true;
    setBusy(true);
    setOutcomes([]);
    try {
      for (const file of files) {
        try {
          const result = await importCustomsReceipt(file);
          changed.current = true;
          setOutcomes((current) => [...current, { name: file.name, kind: "done", result }]);
        } catch (error) {
          const message = error instanceof Error ? error.message : "导入失败，请核对文件后重试";
          setOutcomes((current) => [...current, { name: file.name, kind: "failed", message }]);
        }
      }
      setFiles([]);
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }

  return (
    <Dialog title="导入海关回执" busy={busy} className="cm-import" onClose={() => onClose(changed.current)}>
      <div className="cm-import__body">
        <p className="cm-muted">
          上传单一窗口导出的报关单明细，系统按出口报关单号匹配 NS 报关单并比对明细；境外收货人随回执保存。
          同一报关单号再次导入时，内容变化则以新回执替换旧明细。
        </p>
        <FileDropzone
          label="点击选择或拖入海关回执"
          hint="支持 .xlsx / .xls / .csv，可一次选择多个文件，单个不超过 4MB"
          accept={ACCEPT}
          multiple
          disabled={busy}
          onFiles={(picked) => setFiles(picked)}
        />
        {files.length > 0 && (
          <p className="cm-import__picked">
            已选择 {files.length} 个文件：{files.map((file) => file.name).join("、")}
          </p>
        )}
        <div role="status" aria-live="polite">
          {busy && (
            <p className="cm-muted">
              正在导入并比对，已完成 {outcomes.length} / {files.length} 个文件…
            </p>
          )}
        </div>
        {outcomes.map((outcome, index) =>
          outcome.kind === "failed" ? (
            <Alert key={`${index}-${outcome.name}`} tone="danger" title={`${outcome.name} 未导入`}>
              {outcome.message}
            </Alert>
          ) : (
            <ImportOutcome key={`${index}-${outcome.name}`} result={outcome.result} />
          ),
        )}
      </div>
      <footer className="cm-import__footer">
        <Button disabled={busy} onClick={() => onClose(changed.current)}>
          {outcomes.length ? "关闭并查看结果" : "取消"}
        </Button>
        <Button variant="primary" disabled={busy || !files.length} onClick={() => void upload()}>
          {busy ? "导入中…" : "导入并匹配"}
        </Button>
      </footer>
    </Dialog>
  );
}

function ImportOutcome({ result }: { result: CustomsImportResult }) {
  return (
    <section className="cm-import__outcome" aria-label={`${result.fileName} 导入结果`}>
      <h4>
        {result.fileName}
        <span className="cm-muted">
          {result.rows} 行 · {result.declarations.length} 张报关单 · 新增 {result.created} · 更新{" "}
          {result.replaced} · 内容未变 {result.unchanged}
        </span>
      </h4>
      <p className="cm-muted">
        已识别列：{result.columns.join("、")}
        {result.ignoredColumns.length > 0 && `；未使用：${result.ignoredColumns.join("、")}`}
      </p>
      <DataTable
        label={`${result.fileName} 逐张结果`}
        density="compact"
        minWidth={560}
        maxHeight={260}
        rows={result.declarations}
        rowKey={(row) => row.declarationNo}
        columns={[
          { key: "no", header: "出口报关单号", render: (row) => row.declarationNo },
          { key: "items", header: "项数", align: "right", width: "56px", render: (row) => row.itemCount },
          { key: "result", header: "导入", width: "84px", render: (row) => row.resultLabel },
          {
            key: "status",
            header: "明细比对",
            render: (row) => (
              <Badge tone={consistent(row.status) ? "success" : "warning"}>{row.statusLabel}</Badge>
            ),
          },
          {
            key: "consignee",
            header: "境外收货人",
            render: (row) => <Badge tone={CONSIGNEE_TONE[row.consignee.state]}>{row.consignee.label}</Badge>,
          },
        ]}
      />
    </section>
  );
}
