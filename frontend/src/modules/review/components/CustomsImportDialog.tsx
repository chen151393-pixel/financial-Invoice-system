import { useRef, useState } from "react";
import { Alert, Button, Dialog, FileDropzone } from "../../../shared/components/ui";
import { importCustomsReceipt } from "../customs-api";
import type { CustomsImportJob } from "../customs-types";
import { CustomsImportJobs } from "./CustomsImportJobs";

type FileOutcome = { name: string; kind: "queued" } | { name: string; kind: "failed"; message: string };

const ACCEPT = ".xlsx,.xls,.csv";
/**
 * 导入海关回执：逐个文件上传原文件，展示后端返回的列识别与逐张报关单结果。
 * 上传仅登记后台作业；完成后的持久结果由页面轮询展示，关闭弹窗不取消后台导入。
 */
export function CustomsImportDialog({
  onClose,
  declarationNo,
  jobs,
  progressError,
  onQueued,
}: {
  onClose: () => void;
  declarationNo?: string;
  jobs: CustomsImportJob[];
  progressError: string;
  onQueued: (job: CustomsImportJob) => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [outcomes, setOutcomes] = useState<FileOutcome[]>([]);
  const [busy, setBusy] = useState(false);
  const sending = useRef(false);

  async function upload() {
    if (sending.current || !files.length) return;
    sending.current = true;
    setBusy(true);
    setOutcomes([]);
    try {
      for (const file of files) {
        try {
          const job = await importCustomsReceipt(file);
          onQueued(job);
          setOutcomes((current) => [...current, { name: file.name, kind: "queued" }]);
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
    <Dialog title="导入海关回执" busy={busy} className="cm-import" onClose={onClose}>
      <div className="cm-import__body">
        {declarationNo && <Alert>请上传包含报关单号 {declarationNo} 的海关回执。</Alert>}
        <p className="cm-muted">
          上传单一窗口导出的 24 列报关单明细，后台按出口报关单号匹配 NS
          并比对；尾部空白行、空白列及格式自动忽略。 同一报关单号再次导入时，内容变化则以新回执替换旧明细。
        </p>
        <FileDropzone
          label="点击选择或拖入海关回执"
          hint="支持 .xlsx / .xls / .csv，可多选；上传后后台处理，完成后显示导入结果"
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
              正在上传，已提交 {outcomes.length} / {files.length} 个文件…
            </p>
          )}
        </div>
        {outcomes.map((outcome, index) =>
          outcome.kind === "failed" ? (
            <Alert key={`${index}-${outcome.name}`} tone="danger" title={`${outcome.name} · 上传未确认成功`}>
              {outcome.message}。未确认导入成功，请核对下方后台记录；列表仍可能是原有数据。
            </Alert>
          ) : null,
        )}
        <CustomsImportJobs jobs={jobs} error={progressError} showCompleted />
      </div>
      <footer className="cm-import__footer">
        <Button disabled={busy} onClick={onClose}>
          {outcomes.length ? "关闭" : "取消"}
        </Button>
        <Button variant="primary" disabled={busy || !files.length} onClick={() => void upload()}>
          {busy ? "上传中…" : "上传并后台导入"}
        </Button>
      </footer>
    </Dialog>
  );
}
