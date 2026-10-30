import { useRef, useState, type ReactNode } from "react";
import { Button } from "../Button";
import { BatchUploadResults } from "./BatchUploadResults";
import { Dialog } from "./Dialog";
import { FileDropzone } from "./FileDropzone";
import { ErrorState } from "./States";

/** 后端逐个文件返回的处理结果；target 为后端识别或人工指定的归属编号。 */
export interface BatchUploadResult {
  filename: string;
  target: string;
  status: string;
  reason: string;
  paths: string[];
}
export interface BatchUploadFile {
  file: File;
  target: string;
}
export type BatchUploadRow = { index: number; file: File; result: BatchUploadResult; target: string };

/** 选择或拖入 → 分批上传 → 本次结果；格式、归属和覆盖规则全部以后端为准。 */
export function BatchUpload({
  title,
  help,
  accept,
  targetLabel,
  targetMaxLength,
  statusLabels,
  assignable,
  upload,
  onClose,
  batchSize = 5,
  fileLabel = "文件",
  pickerHint = "可多选或拖入文件",
  intro = "选择文件后上传，仅展示本次处理结果。",
}: {
  title: string;
  help: ReactNode;
  accept: string;
  targetLabel: string;
  targetMaxLength: number;
  statusLabels: Record<string, string>;
  assignable: readonly string[];
  upload: (files: BatchUploadFile[]) => Promise<BatchUploadResult[]>;
  onClose: (changed: boolean) => void;
  batchSize?: number;
  fileLabel?: string;
  pickerHint?: string;
  intro?: string;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [rows, setRows] = useState<BatchUploadRow[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [changed, setChanged] = useState(false);
  const sending = useRef(false);

  async function run(action: () => Promise<void>) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败，请核对后重试");
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  const submit = () =>
    run(async () => {
      if (!files.length) return;
      const selected = files;
      setRows([]);
      for (let start = 0; start < selected.length; start += batchSize) {
        const part = selected.slice(start, start + batchSize);
        const results = await upload(part.map((file) => ({ file, target: "" })));
        // 每批返回即展示；后续批次失败时保留已完成结果与尚未传输的文件。
        setRows((current) => [
          ...current,
          ...results.map((result, index) => ({
            index: start + index,
            file: part[index],
            result,
            target: "",
          })),
        ]);
        setChanged((current) => current || results.some((result) => result.status === "saved"));
        setFiles(selected.slice(start + part.length));
      }
    });
  const resend = (row: BatchUploadRow) =>
    run(async () => {
      const [result] = await upload([{ file: row.file, target: row.target.trim() }]);
      setRows((current) => current.map((item) => (item.index === row.index ? { ...item, result } : item)));
      setChanged((current) => current || result.status === "saved");
    });

  return (
    <Dialog className="ui-upload-dialog" title={title} busy={busy} onClose={() => onClose(changed)}>
      <div className="ui-upload">
        <p className="ui-upload__help">{intro}</p>
        <FileDropzone
          label={`点击选择或拖入${fileLabel}`}
          hint={pickerHint}
          accept={accept}
          multiple
          disabled={busy}
          onFiles={(selected) => setFiles((current) => [...current, ...selected])}
        />
        {files.length > 0 && (
          <section className="ui-upload__selection" aria-label="已选文件">
            <div className="ui-upload__heading">
              <strong>已选 {files.length} 个文件</strong>
              <Button size="sm" variant="ghost" disabled={busy} onClick={() => setFiles([])}>
                清空选择
              </Button>
            </div>
            <ul>
              {files.map((file, index) => (
                <li key={index}>
                  <span>{file.name}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={busy}
                    aria-label={`移除文件 ${file.name}`}
                    onClick={() => setFiles((current) => current.filter((_, i) => i !== index))}
                  >
                    移除
                  </Button>
                </li>
              ))}
            </ul>
          </section>
        )}
        <div className="ui-upload__actions">
          <Button variant="primary" disabled={busy || !files.length} onClick={() => void submit()}>
            {busy ? "正在上传…" : files.length ? `开始上传 ${files.length} 个文件` : "开始上传"}
          </Button>
          <span className="ui-upload__help">
            {busy ? "上传期间请保持窗口打开" : "重新打开窗口时清空上次展示"}
          </span>
        </div>
        <details className="ui-upload__rules">
          <summary>上传说明</summary>
          <div className="ui-upload__help">{help}</div>
        </details>
        {error && <ErrorState title="上传操作失败" message={error} />}
        {rows.length > 0 && (
          <section className="ui-upload__results" aria-label="本次处理结果">
            <h4>本次处理结果</h4>
            <BatchUploadResults
              rows={rows}
              busy={busy}
              targetLabel={targetLabel}
              targetMaxLength={targetMaxLength}
              statusLabels={statusLabels}
              assignable={assignable}
              onAssign={(index, target) =>
                setRows((current) =>
                  current.map((item) => (item.index === index ? { ...item, target } : item)),
                )
              }
              onRetry={(row) => void resend(row)}
            />
          </section>
        )}
      </div>
    </Dialog>
  );
}
