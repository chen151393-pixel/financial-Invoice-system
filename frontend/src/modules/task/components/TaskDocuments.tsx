import { Button } from "../../../shared/components/Button";
import type { DeclarationDocumentType, TaskDetail, TaskDocument } from "../types/task";
import { DeclarationDocuments } from "./DeclarationDocuments";
import { formatTime } from "./format";
import { SignedContracts } from "./SignedContracts";
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
  onRetryDeclaration,
  onUploadSigned,
  onNotify,
}: {
  detail: TaskDetail;
  busy: string | null;
  onPrepare: (orderId: string) => void;
  onRetryDeclaration: (type: DeclarationDocumentType) => void;
  onUploadSigned: () => void;
  onNotify: () => void;
}) {
  const superseded = detail.sourceStatus === "superseded";
  return (
    <div className="itd-content">
      <div>
        <h3>子采购合同</h3>
        <p className="it-help">
          合同保存到共享盘“月份/CD号_真实报关单号”文件夹，文件名为“子采购单号_供应商简称_真实报关单号.pdf”；全部保存后即可通知供应商。
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
      <DeclarationDocuments
        documents={detail.declarationDocuments}
        busy={busy}
        onRetry={onRetryDeclaration}
      />
      <SignedContracts
        contracts={detail.signedContracts}
        disabled={superseded || busy !== null}
        onUpload={onUploadSigned}
      />
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
