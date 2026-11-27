import type { TaskDetail } from "../types/task";
import { formatTime } from "./format";

export function TaskHistory({ detail }: { detail: TaskDetail }) {
  // 统一排列流程事件与合同获取记录，避免最新的合同操作固定落在历史末尾。
  const records = [
    ...detail.events.map((event, index) => ({
      kind: "event" as const,
      key: `event:${index}`,
      at: event.at,
      event,
    })),
    ...detail.documents
      .filter((doc) => doc.downloadedAt)
      .map((doc) => ({
        kind: "document" as const,
        key: `document:${doc.taskId || ""}:${doc.orderId}`,
        at: doc.downloadedAt!,
        doc,
      })),
  ].sort((left, right) => Date.parse(right.at) - Date.parse(left.at));

  return (
    <div className="itd-history-wrap">
      <ol className="itd-history">
        {records.map((record) => (
          <li key={record.key}>
            {record.kind === "event" ? (
              <>
                <strong>{record.event.label}</strong>
                <p>
                  {formatTime(record.at)} · 操作人{" "}
                  {record.event.actor === "system" ? "系统" : record.event.actor}
                </p>
                {record.event.reason && <p>{record.event.reason}</p>}
              </>
            ) : (
              <>
                <strong>获取子采购合同：{record.doc.orderNumber}</strong>
                <p>
                  {formatTime(record.at)} · NS {record.doc.environment} / {record.doc.nsId}
                </p>
                {record.doc.archivedAt && <p>保存到共享盘：{formatTime(record.doc.archivedAt)}</p>}
                {record.doc.archivePath && <p className="it-reference">{record.doc.archivePath}</p>}
                <p className="it-reference">文件 SHA-256：{record.doc.sha256}</p>
              </>
            )}
          </li>
        ))}
      </ol>
      <p className="it-reference">任务编号：{detail.task.id}</p>
    </div>
  );
}
