import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  Progress,
  Skeleton,
} from "../../../shared/components/ui";
import { useSignedUploads } from "../hooks/useSignedUploads";
import { UPLOAD_STATUS, type UploadBatch } from "../types/signed-upload";
import { NotificationDialog } from "./NotificationDialog";
import "./signed-contract-upload.css";

/** 上传传输和后台归档分开展示；关闭后可重新打开查看持久任务。 */
export function SignedContractUpload({ onClose }: { onClose: (changed: boolean) => void }) {
  const [files, setFiles] = useState<File[]>([]);
  const [orders, setOrders] = useState<Record<string, string>>({});
  const state = useSignedUploads();
  const changed = state.jobs.some((job) => job.saved > 0);

  function results(job: UploadBatch) {
    return (
      <section key={job.id} className="itd-upload__job" aria-label={`上传任务 ${job.id}`}>
        <h4>任务 {job.id.slice(0, 8)}</h4>
        <Progress label="文件传输进度" width={job.uploadPercent} text={`文件传输 ${job.uploadPercent}%`} />
        <Progress label="后台处理进度" width={job.progressPercent} text={job.message} />
        <DataTable
          label="逐文件处理结果"
          rowKey={(row) => row.id}
          rows={job.items}
          columns={[
            { key: "filename", header: "文件", render: (row) => row.filename },
            {
              key: "status",
              header: "状态",
              render: (row) => (
                <Badge tone={row.status === "saved" ? "success" : row.canRetry ? "warning" : "info"}>
                  {UPLOAD_STATUS[row.status]}
                </Badge>
              ),
            },
            {
              key: "result",
              header: "说明",
              render: (row) => (
                <>
                  {state.transfers[row.id] ||
                    row.reason ||
                    (row.status === "uploading"
                      ? "等待文件传输完成；页面关闭后需重新选择未传完的文件"
                      : "后端正在处理，可关闭窗口")}
                  {row.archivePath && <span className="it-secondary">{row.archivePath}</span>}
                </>
              ),
            },
            {
              key: "action",
              header: "子采购单 / 操作",
              render: (row) =>
                row.canRetry ? (
                  <span className="itd-upload__assign">
                    <input
                      aria-label={`指定子采购单号：${row.filename}`}
                      placeholder="子采购单号（可选）"
                      maxLength={150}
                      value={orders[row.id] ?? row.orderNumber}
                      disabled={state.busy}
                      onChange={(event) =>
                        setOrders((current) => ({ ...current, [row.id]: event.target.value }))
                      }
                    />
                    <Button
                      size="sm"
                      disabled={state.busy}
                      onClick={() => void state.retry(job, row.id, orders[row.id] ?? row.orderNumber)}
                    >
                      重新排队
                    </Button>
                  </span>
                ) : row.status === "uploading" && state.canResume(row.id) ? (
                  <Button size="sm" disabled={state.busy} onClick={() => void state.retry(job, row.id, "")}>
                    继续上传
                  </Button>
                ) : (
                  row.orderNumber || "—"
                ),
            },
          ]}
        />
      </section>
    );
  }

  return (
    <NotificationDialog title="批量上传回签合同" busy={state.busy} onClose={() => onClose(changed)}>
      <div className="itd-upload">
        <Alert tone="info" title="单个文件最高 100 MB">
          支持 PDF、JPG、PNG。文件逐个上传，完整接收后自动进入后台队列；单个失败不影响其他文件。
          文件传输期间请保持页面打开，传完后可关闭，重新打开本窗口查看最近任务。
          文件名需包含子采购单号；已有不同内容的回签合同不会覆盖。
        </Alert>
        <label className="itd-upload__picker">
          选择回签合同
          <input
            type="file"
            multiple
            accept=".pdf,.jpg,.jpeg,.png"
            disabled={state.busy}
            onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
          />
        </label>
        <div className="itd-upload__actions">
          <Button
            variant="primary"
            disabled={state.busy || files.length === 0}
            onClick={() =>
              void state.submit(files).then((accepted) => {
                if (accepted) setFiles([]);
              })
            }
          >
            {state.busy ? "正在传输文件…" : `上传 ${files.length} 个文件并排队`}
          </Button>
          <Button disabled={state.busy} onClick={() => void state.refresh()}>
            刷新任务
          </Button>
        </div>
        {state.error && (
          <ErrorState
            title="上传任务操作失败"
            message={state.error}
            action={
              <Button disabled={state.busy} onClick={() => void state.refresh()}>
                重新查询
              </Button>
            }
          />
        )}
        {state.loading && <Skeleton rows={3} label="正在读取上传任务" />}
        {!state.loading && !state.error && state.jobs.length === 0 && (
          <EmptyState title="暂无上传任务" description="选择合同文件后提交，处理结果会逐个显示。" />
        )}
        {state.jobs.map(results)}
      </div>
    </NotificationDialog>
  );
}
