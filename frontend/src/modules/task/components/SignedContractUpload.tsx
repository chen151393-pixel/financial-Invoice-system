import { useState } from "react";
import { readImportFile } from "../../../shared/api/import-file";
import { Button } from "../../../shared/components/Button";
import type { SignedUploadFile, SignedUploadItem } from "../types/task";
import { NotificationDialog } from "./NotificationDialog";
import "./signed-contract-upload.css";

const STATUS: Record<SignedUploadItem["status"], string> = {
  saved: "已保存",
  unmatched: "未识别单号",
  ambiguous: "匹配多个单号",
  conflict: "已有不同文件，未覆盖",
  failed: "未保存",
};
// 单次请求文件数与后端限制一致；更多文件分批提交
const BATCH = 5;

type Row = { file: File; result: SignedUploadItem; orderNo: string };

/** 回签合同批量上传窗口：只读取文件并提交，归属、格式与覆盖规则以后端结果为准。 */
export function SignedContractUpload({
  upload,
  onClose,
}: {
  upload: (files: SignedUploadFile[]) => Promise<{ items: SignedUploadItem[] }>;
  onClose: (changed: boolean) => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(selected: File[], orderNos: string[]) {
    const results: SignedUploadItem[] = [];
    for (let start = 0; start < selected.length; start += BATCH) {
      const part = selected.slice(start, start + BATCH);
      const read = await Promise.all(part.map(readImportFile));
      const body = read.map((item, index) => ({ ...item, orderNo: orderNos[start + index] ?? "" }));
      results.push(...(await upload(body)).items);
    }
    return results;
  }

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const results = await send(files, []);
      setRows(results.map((result, index) => ({ file: files[index], result, orderNo: "" })));
      setFiles([]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败，请核对后重试");
    } finally {
      setBusy(false);
    }
  }

  async function resend(index: number) {
    const row = rows[index];
    setBusy(true);
    setError("");
    try {
      const [result] = await send([row.file], [row.orderNo.trim()]);
      setRows((current) => current.map((item, i) => (i === index ? { ...item, result } : item)));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "上传失败，请核对后重试");
    } finally {
      setBusy(false);
    }
  }

  const changed = rows.some((row) => row.result.status === "saved");
  return (
    <NotificationDialog title="批量上传回签合同" busy={busy} onClose={() => onClose(changed)}>
      <div className="itd-upload">
        <p className="it-help">
          支持 PDF、JPG、PNG，单个文件不超过 10
          MB。文件名需包含子采购单号，系统据此保存到“月份/CD号_真实报关单号”文件夹；同一子采购单已上传不同文件时不会覆盖。
        </p>
        <label className="itd-upload__picker">
          选择文件
          <input
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png"
            disabled={busy}
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
        </label>
        <Button variant="primary" disabled={busy || files.length === 0} onClick={() => void submit()}>
          {busy ? "正在上传…" : `上传 ${files.length} 个文件`}
        </Button>
        {error && (
          <p className="itd-feedback" role="alert">
            {error}
          </p>
        )}
        {rows.length > 0 && (
          <div className="it-table-wrap" role="region" aria-label="回签合同上传结果，可横向滚动">
            <table>
              <caption className="itd-upload__caption">上传结果</caption>
              <thead>
                <tr>
                  <th scope="col">文件</th>
                  <th scope="col">子采购单</th>
                  <th scope="col">结果</th>
                  <th scope="col">说明</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.file.name}-${index}`}>
                    <td>{row.result.filename}</td>
                    <td>
                      {row.result.status === "unmatched" || row.result.status === "ambiguous" ? (
                        <span className="itd-upload__assign">
                          <input
                            aria-label={`指定子采购单号：${row.result.filename}`}
                            value={row.orderNo}
                            maxLength={150}
                            disabled={busy}
                            onChange={(event) =>
                              setRows((current) =>
                                current.map((item, i) =>
                                  i === index ? { ...item, orderNo: event.target.value } : item,
                                ),
                              )
                            }
                          />
                          <Button disabled={busy || !row.orderNo.trim()} onClick={() => void resend(index)}>
                            按此单号上传
                          </Button>
                        </span>
                      ) : (
                        row.result.orderNumber || "—"
                      )}
                    </td>
                    <td>{STATUS[row.result.status]}</td>
                    <td>
                      {row.result.reason}
                      {row.result.archivePath && (
                        <span className="it-secondary">{row.result.archivePath}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </NotificationDialog>
  );
}
