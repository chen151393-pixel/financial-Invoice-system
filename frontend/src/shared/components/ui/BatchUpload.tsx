import { useState, type ReactNode } from "react";
import { Button } from "../Button";
import { DataTable } from "./DataTable";
import { Dialog } from "./Dialog";

/** 后端逐个文件返回的处理结果；target 为后端识别或人工指定的归属编号（单号、发票号码等）。 */
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

type Row = { index: number; file: File; result: BatchUploadResult; target: string };

/**
 * 批量上传窗口：选择文件 → 分批提交 → 逐个展示真实结果；识别不了归属的文件可填写编号后单独重传。
 * 归属、格式与覆盖规则全部以后端结果为准，组件不判断文件能否保存。
 */
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
}: {
  title: string;
  help: ReactNode;
  accept: string;
  /** 结果表中归属编号一列的名称，如“子采购单”“发票号码” */
  targetLabel: string;
  targetMaxLength: number;
  statusLabels: Record<string, string>;
  /** 允许人工填写编号后重传的状态 */
  assignable: readonly string[];
  upload: (files: BatchUploadFile[]) => Promise<BatchUploadResult[]>;
  /** changed：本次是否至少保存成功一个文件 */
  onClose: (changed: boolean) => void;
  /** 单次请求的文件数，与后端限制一致；更多文件分批提交 */
  batchSize?: number;
}) {
  const [files, setFiles] = useState<File[]>([]);
  // 提交后重建文件选择框，清空已提交的选择
  const [picker, setPicker] = useState(0);
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(selected: BatchUploadFile[]) {
    const results: BatchUploadResult[] = [];
    for (let start = 0; start < selected.length; start += batchSize) {
      results.push(...(await upload(selected.slice(start, start + batchSize))));
    }
    return results;
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败，请核对后重试");
    } finally {
      setBusy(false);
    }
  }

  const submit = () =>
    run(async () => {
      const results = await send(files.map((file) => ({ file, target: "" })));
      setRows(results.map((result, index) => ({ index, file: files[index], result, target: "" })));
      setFiles([]);
      setPicker((value) => value + 1);
    });

  const resend = (row: Row) =>
    run(async () => {
      const [result] = await send([{ file: row.file, target: row.target.trim() }]);
      setRows((current) => current.map((item) => (item.index === row.index ? { ...item, result } : item)));
    });

  function assign(row: Row) {
    return (
      <span className="ui-upload__assign">
        <input
          aria-label={`指定${targetLabel}：${row.result.filename}`}
          value={row.target}
          maxLength={targetMaxLength}
          disabled={busy}
          onChange={(event) =>
            setRows((current) =>
              current.map((item) =>
                item.index === row.index ? { ...item, target: event.target.value } : item,
              ),
            )
          }
        />
        <Button disabled={busy || !row.target.trim()} onClick={() => void resend(row)}>
          按此编号上传
        </Button>
      </span>
    );
  }

  const changed = rows.some((row) => row.result.status === "saved");
  return (
    <Dialog title={title} busy={busy} onClose={() => onClose(changed)}>
      <div className="ui-upload">
        <p className="ui-upload__help">{help}</p>
        <label className="ui-upload__picker">
          选择文件
          <input
            key={picker}
            type="file"
            multiple
            accept={accept}
            disabled={busy}
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
        </label>
        <Button variant="primary" disabled={busy || files.length === 0} onClick={() => void submit()}>
          {busy ? "正在上传…" : `上传 ${files.length} 个文件`}
        </Button>
        {error && (
          <p className="ui-upload__error" role="alert">
            {error}
          </p>
        )}
        {rows.length > 0 && (
          <DataTable
            label={`${title}结果`}
            minWidth={560}
            rows={rows}
            rowKey={(row) => String(row.index)}
            columns={[
              { key: "file", header: "文件", width: "28%", render: (row) => row.result.filename },
              {
                key: "target",
                header: targetLabel,
                width: "26%",
                render: (row) =>
                  assignable.includes(row.result.status) ? assign(row) : row.result.target || "—",
              },
              {
                key: "status",
                header: "结果",
                width: "14%",
                render: (row) => statusLabels[row.result.status] ?? row.result.status,
              },
              {
                key: "reason",
                header: "说明",
                render: (row) => (
                  <>
                    {row.result.reason}
                    {row.result.paths.map((path) => (
                      <span key={path} className="ui-upload__path">
                        {path}
                      </span>
                    ))}
                  </>
                ),
              },
            ]}
          />
        )}
      </div>
    </Dialog>
  );
}
