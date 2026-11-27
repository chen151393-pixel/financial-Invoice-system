import type { TaskDetail } from "../types/task";
import { EmptyState } from "../../../shared/components/ui";
import { formatTime } from "./format";

export function TaskHistory({ detail }: { detail: TaskDetail }) {
  return (
    <div className="itd-history-wrap">
      {detail.history.length === 0 && <EmptyState title="暂无流转记录" />}
      <ol className="itd-history" reversed aria-label="流转记录，最新操作在前">
        {detail.history.map((record) => (
          <li key={record.id} value={record.sequence}>
            <strong>{record.label}</strong>
            {record.kind === "event" ? (
              <>
                <p>
                  {formatTime(record.at)} · 操作人 <span title={record.actor}>{record.actorName}</span>
                </p>
                {record.reason && <p>{record.reason}</p>}
              </>
            ) : (
              <>
                <p>
                  {formatTime(record.at)} · NS {record.environment} / {record.nsId}
                </p>
                {record.archivedAt && <p>保存到共享盘：{formatTime(record.archivedAt)}</p>}
                {record.archivePath && <p className="it-reference">{record.archivePath}</p>}
                <p className="it-reference">文件 SHA-256：{record.sha256}</p>
              </>
            )}
          </li>
        ))}
      </ol>
      <p className="it-reference">任务编号：{detail.task.id}</p>
    </div>
  );
}
