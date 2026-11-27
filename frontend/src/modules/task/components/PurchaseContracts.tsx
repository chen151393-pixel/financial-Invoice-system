import { Badge, Button, DataTable, EmptyState, type Tone } from "../../../shared/components/ui";
import type { TaskDocument } from "../types/task";
import { formatTime } from "./format";
import "./task-materials.css";

const TONES: Record<TaskDocument["status"], Tone> = {
  ready: "success",
  pending: "warning",
  failed: "danger",
};
const LABELS = { ready: "已保存到共享盘", pending: "待保存", failed: "保存失败" };

/** 合同与原报关单对应展示，文件路径与来源收在详情里，不生成无下载接口的假链接。 */
export function PurchaseContracts({
  documents,
  busy,
  onPrepare,
  label = "子采购合同归档清单",
  pathOnly = false,
}: {
  documents: TaskDocument[];
  busy?: string | null;
  onPrepare?: (orderId: string) => void;
  label?: string;
  pathOnly?: boolean;
}) {
  if (!documents.length)
    return <EmptyState title="暂无子采购合同" description="此任务没有可下载的子采购订单。" />;
  return (
    <DataTable
      label={label}
      rows={documents}
      rowKey={(doc) => `${doc.taskId ?? ""}:${doc.orderId}`}
      minWidth={640}
      density="compact"
      columns={[
        {
          key: "order",
          header: pathOnly ? "子采购单 / 保存路径" : "子采购单 / 合同文件",
          width: "44%",
          render: (doc) =>
            pathOnly ? (
              <div className="it-materials__file">
                <strong>{doc.orderNumber || "子采购单编号缺失"}</strong>
                <span>{doc.archivePath || "尚未归档，暂无保存路径"}</span>
              </div>
            ) : (
              <div className="it-materials__file">
                <strong>{doc.orderNumber || "子采购单编号缺失"}</strong>
                <span>{doc.filename ? `PDF ${doc.filename}` : "合同尚未归档"}</span>
                {(doc.archivePath || doc.archivedAt) && (
                  <details>
                    <summary>归档详情</summary>
                    {doc.archivedAt && <p>归档时间：{formatTime(doc.archivedAt)}</p>}
                    <p>
                      来源环境：{doc.environment || "未配置"}
                      {doc.nsId ? ` · 文件 ${doc.nsId}` : ""}
                    </p>
                    {doc.archivePath && <p>保存路径：{doc.archivePath}</p>}
                  </details>
                )}
              </div>
            ),
        },
        {
          key: "record",
          header: "报关单",
          width: "25%",
          render: (doc) => (
            <div className="it-materials__file">
              <span>{doc.recordNumber || "CD 号缺失"}</span>
              {doc.declarationNumber && <span>{doc.declarationNumber}</span>}
            </div>
          ),
        },
        {
          key: "status",
          header: "归档状态",
          render: (doc) => (
            <div className="it-materials__file">
              <span>
                <Badge tone={TONES[doc.status]}>{LABELS[doc.status]}</Badge>
              </span>
              {doc.error && (
                <p className="it-materials__error" role="alert">
                  {doc.error}
                </p>
              )}
              {doc.status !== "ready" && onPrepare && (
                <>
                  <span>
                    <Button
                      size="sm"
                      disabled={!doc.prepare.allowed || busy != null}
                      onClick={() => onPrepare(doc.orderId)}
                    >
                      {busy === doc.orderId
                        ? "正在保存…"
                        : doc.status === "failed"
                          ? "重试保存"
                          : "保存到共享盘"}
                    </Button>
                  </span>
                </>
              )}
              {doc.status !== "ready" && !doc.prepare.allowed && <span>{doc.prepare.reason}</span>}
            </div>
          ),
        },
      ]}
    />
  );
}
