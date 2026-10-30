import { useState } from "react";
import { Badge, Button, DataTable, Progress } from "../../../shared/components/ui";
import { UPLOAD_STATUS, type UploadBatch } from "../types/signed-upload";

/** 只展示本次提交的一批文件；归档路径收起，优先呈现可处理的结果。 */
export function SignedUploadResults({
  job,
  index,
  busy,
  transfers,
  canResume,
  onRetry,
}: {
  job: UploadBatch;
  index: number;
  busy: boolean;
  transfers: Record<string, string>;
  canResume: (id: string) => boolean;
  onRetry: (job: UploadBatch, fileId: string, orderNo: string) => void;
}) {
  const [orders, setOrders] = useState<Record<string, string>>({});
  return (
    <section className="itd-upload__job" aria-label={`本次第 ${index + 1} 批文件结果`}>
      <div className="itd-upload__job-heading">
        <strong>第 {index + 1} 批</strong>
        <Badge tone={job.phase === "completed" ? "neutral" : "info"} dot={false}>
          {job.phase === "completed" ? "处理结束" : "处理中"}
        </Badge>
      </div>
      <p className="itd-upload__message" role="status">
        {job.message}
      </p>
      {job.phase !== "completed" && (
        <>
          {job.uploadPercent < 100 && (
            <Progress
              label="文件传输进度"
              width={job.uploadPercent}
              text={`文件传输 ${job.uploadPercent}%`}
            />
          )}
          <Progress label="后台处理进度" width={job.progressPercent} text="文件完整接收后自动归档" />
        </>
      )}
      <DataTable
        label="本次逐文件处理结果"
        minWidth={0}
        density="compact"
        rowKey={(row) => row.id}
        rows={job.items}
        columns={[
          {
            key: "file",
            header: "合同文件 / 子采购单",
            width: "46%",
            render: (row) => (
              <>
                <strong className="itd-upload__filename">{row.filename}</strong>
                <span className="itd-upload__muted">{row.orderNumber || "子采购单待识别"}</span>
              </>
            ),
          },
          {
            key: "result",
            header: "处理结果",
            render: (row) => (
              <>
                <Badge
                  tone={
                    row.status === "saved"
                      ? "success"
                      : row.canRetry || transfers[row.id]
                        ? "warning"
                        : "info"
                  }
                >
                  {transfers[row.id] ? "传输中断" : UPLOAD_STATUS[row.status]}
                </Badge>
                <p className="itd-upload__reason">
                  {transfers[row.id] ||
                    row.reason ||
                    (row.status === "uploading" ? "正在等待文件传输" : "后台正在处理")}
                </p>
                {row.archivePath && (
                  <details className="itd-upload__path">
                    <summary>查看保存位置</summary>
                    <span>{row.archivePath}</span>
                  </details>
                )}
                {row.canRetry ? (
                  <div className="itd-upload__assign">
                    <input
                      aria-label={`指定子采购单号：${row.filename}`}
                      placeholder="子采购单号（可选）"
                      maxLength={150}
                      value={orders[row.id] ?? row.orderNumber}
                      disabled={busy}
                      onChange={(event) =>
                        setOrders((current) => ({ ...current, [row.id]: event.target.value }))
                      }
                    />
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => onRetry(job, row.id, orders[row.id] ?? row.orderNumber)}
                    >
                      重新处理
                    </Button>
                  </div>
                ) : row.status === "uploading" && canResume(row.id) && transfers[row.id] ? (
                  <Button size="sm" disabled={busy} onClick={() => onRetry(job, row.id, "")}>
                    继续上传
                  </Button>
                ) : null}
              </>
            ),
          },
        ]}
      />
    </section>
  );
}
