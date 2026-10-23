import { Button } from "../../../shared/components/Button";
import type { DeclarationDocument, DeclarationDocumentType } from "../types/task";
import { formatTime } from "./format";

/** 报关资料：按报关单各一份，由 NS 下载；失败不影响通知供应商，可单独重试或重新下载。 */
export function DeclarationDocuments({
  documents,
  busy,
  onRetry,
}: {
  documents: DeclarationDocument[];
  busy: string | null;
  onRetry: (type: DeclarationDocumentType) => void;
}) {
  return (
    <div>
      <h3>报关资料</h3>
      <p className="it-help">
        报关单、销售合同、发票由 NS
        下载，与子采购合同保存在同一报关单文件夹；下载失败不影响通知供应商，但资料到齐前任务不会完结。
      </p>
      {documents.map((doc) => (
        <div key={doc.type} className="itd-document">
          <span className="itd-file-type" aria-hidden="true">
            PDF
          </span>
          <div className="itd-document__info">
            <strong>{doc.label}</strong>
            <p>
              {doc.statusLabel}
              {doc.archivedAt ? ` · ${formatTime(doc.archivedAt)}` : ""}
              {doc.attempts > 0 ? ` · 已尝试 ${doc.attempts} 次` : ""}
            </p>
            {doc.error && <p className="itd-document__error">失败原因：{doc.error}</p>}
            {doc.files.map((file) => (
              <p key={file.path} className="it-reference">
                保存路径：{file.path}
              </p>
            ))}
            {!doc.retry.allowed && <p>{doc.retry.reason}</p>}
          </div>
          <Button
            variant={doc.status === "archived" ? "secondary" : "primary"}
            disabled={!doc.retry.allowed || busy !== null}
            title={doc.retry.reason}
            aria-label={`${doc.status === "archived" ? "重新下载" : "下载"}${doc.label}`}
            onClick={() => onRetry(doc.type)}
          >
            {busy === doc.type
              ? "正在下载…"
              : doc.status === "archived"
                ? "重新下载"
                : doc.status === "failed"
                  ? "重试下载"
                  : "立即下载"}
          </Button>
        </div>
      ))}
    </div>
  );
}
