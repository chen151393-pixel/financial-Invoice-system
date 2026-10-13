import type { TaskDetail } from "../types/task";
import { formatTime } from "./format";

export function TaskHistory({ detail }: { detail: TaskDetail }) {
  return (
    <div className="itd-content">
      <h3>已发生的流程记录</h3>
      <ol className="itd-history">
        {detail.events.map((event, index) => (
          <li key={`${event.at}:${index}`}>
            <strong>{event.label}</strong>
            <p>
              {formatTime(event.at)} · 操作人 {event.actor === "system" ? "系统" : event.actor}
            </p>
            {event.reason && <p>{event.reason}</p>}
          </li>
        ))}
        {detail.documents
          .filter((doc) => doc.downloadedAt)
          .map((doc) => (
            <li key={doc.orderId}>
              <strong>获取子采购合同：{doc.orderNumber}</strong>
              <p>
                {formatTime(doc.downloadedAt!)} · NS {doc.environment} / {doc.nsId}
              </p>
              {doc.archivedAt && <p>保存到共享盘：{formatTime(doc.archivedAt)}</p>}
              {doc.archivePath && <p className="it-reference">{doc.archivePath}</p>}
              <p className="it-reference">文件 SHA-256：{doc.sha256}</p>
            </li>
          ))}
      </ol>
      <p className="it-reference">任务编号：{detail.task.id}</p>
    </div>
  );
}
