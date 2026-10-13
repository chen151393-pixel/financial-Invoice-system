import { Button } from "../../../shared/components/Button";
import type { TaskDetail, TaskDocument } from "../types/task";
import { formatTime } from "./format";
import { TaskLines } from "./TaskLines";

function documentStatus(doc: TaskDocument) {
  if (doc.status === "ready")
    return `已保存到共享盘 · ${formatTime(doc.archivedAt!)} · NS ${doc.environment} / ${doc.nsId}`;
  if (doc.status === "failed") return `保存失败：${doc.error || "请重试"}`;
  return `待保存 · NS 环境 ${doc.environment || "未配置"}`;
}

export function TaskDocuments({
  detail,
  busy,
  onPrepare,
  onNotify,
}: {
  detail: TaskDetail;
  busy: string | null;
  onPrepare: (orderId: string) => void;
  onNotify: () => void;
}) {
  return (
    <div className="itd-content">
      <div>
        <h3>子采购合同</h3>
        <p className="it-help">
          合同统一保存到共享盘，按首次获取日期建立文件夹，文件名为“子采购订单号+供应商.pdf”。
        </p>
      </div>
      {detail.documents.length === 0 && <p>此任务没有可下载的子采购订单。</p>}
      {detail.documents.map((doc) => (
        <div key={doc.orderId} className="itd-document">
          <span className="itd-file-type" aria-hidden="true">
            PDF
          </span>
          <div className="itd-document__info">
            <strong>{doc.orderNumber || "子采购单编号缺失"}</strong>
            <p>{documentStatus(doc)}</p>
            <p>{doc.prepare.reason}</p>
            {doc.archivePath && <p className="it-reference">保存路径：{doc.archivePath}</p>}
          </div>
          {doc.status !== "ready" && (
            <Button
              variant="primary"
              disabled={!doc.prepare.allowed || busy !== null}
              onClick={() => onPrepare(doc.orderId)}
            >
              {busy === doc.orderId ? "正在保存到共享盘…" : "保存到共享盘"}
            </Button>
          )}
        </div>
      ))}
      {detail.reasons.map((reason) => (
        <p className="it-help" key={reason}>
          {reason}
        </p>
      ))}
      <TaskLines lines={detail.lines} />
      <div className="itd-next">
        <div>
          <h3>下一步：通知供应商开票</h3>
          <p>{detail.notify.reason}</p>
        </div>
        <Button onClick={onNotify}>通知供应商</Button>
      </div>
    </div>
  );
}
