import { Badge, Button, DataTable, EmptyState, type Tone } from "../../../shared/components/ui";
import type { DeclarationDocument, DeclarationDocumentType, TaskDeclarationRow } from "../types/task";
import { formatTime } from "./format";
import "./task-materials.css";

const TONES: Record<DeclarationDocument["status"], Tone> = {
  archived: "success",
  pending: "warning",
  unregistered: "neutral",
  failed: "danger",
};
type Retry = (type: DeclarationDocumentType, taskId?: string) => void;

/** 每张报关单一行，各文件保留自己的真实状态、来源和重试任务。销售合同只展示状态。 */
export function DeclarationDocuments({
  groups,
  busy,
  onRetry,
  count,
}: {
  groups: TaskDeclarationRow[];
  busy: string | null;
  onRetry: Retry;
  count?: number;
}) {
  function cell(doc: DeclarationDocument | null) {
    if (!doc) return <span className="it-help">状态待获取</span>;
    const status = <Badge tone={TONES[doc.status]}>{doc.statusLabel}</Badge>;
    if (doc.type === "sales_contract") return status;
    return (
      <div className="it-materials__file">
        <span>{status}</span>
        {doc.status === "archived" ? (
          <details>
            <summary>文件与操作</summary>
            <Files doc={doc} />
            <DeclarationAction doc={doc} busy={busy} onRetry={onRetry} />
          </details>
        ) : (
          <>
            {doc.attempts > 0 && <span>已尝试 {doc.attempts} 次</span>}
            {doc.error && (
              <p className="it-materials__error" role="alert">
                失败原因：{doc.error}
              </p>
            )}
            <DeclarationAction doc={doc} busy={busy} onRetry={onRetry} />
          </>
        )}
      </div>
    );
  }
  return (
    <section className="it-materials it-materials__section" aria-label="报关资料">
      <div className="it-materials__heading">
        <h4>报关资料</h4>
        <span className="it-help">按报关单分别保留{count !== undefined ? `，共 ${count} 组` : ""}</span>
      </div>
      {groups.length ? (
        <DataTable
          label="报关资料清单"
          rows={groups}
          rowKey={(row) => row.taskId}
          minWidth={680}
          density="compact"
          columns={[
            {
              key: "record",
              header: "报关单",
              width: "25%",
              render: (row) => (
                <div className="it-materials__file">
                  <strong>{row.recordNumber || "CD 号缺失"}</strong>
                  {row.declarationNumber && <span>{row.declarationNumber}</span>}
                </div>
              ),
            },
            { key: "customs", header: "报关单文件", render: (row) => cell(row.customs) },
            { key: "sales", header: "销售合同", render: (row) => cell(row.sales) },
            { key: "invoice", header: "发票文件", render: (row) => cell(row.invoice) },
          ]}
        />
      ) : (
        <EmptyState title="暂无报关资料" description="请刷新任务详情，读取对应报关单的资料状态。" />
      )}
      <p className="it-help">报关单、发票由 NS 下载；下载失败不影响通知供应商，但资料到齐前任务不会完结。</p>
    </section>
  );
}

function DeclarationAction({
  doc,
  busy,
  onRetry,
}: {
  doc: DeclarationDocument;
  busy: string | null;
  onRetry: Retry;
}) {
  const running = busy === doc.taskId + ":" + doc.type;
  return (
    <>
      <span>
        <Button
          size="sm"
          disabled={!doc.retry.allowed || busy !== null}
          title={doc.retry.reason}
          aria-label={
            (doc.recordNumber || "") + " " + (doc.status === "archived" ? "重新下载" : "下载") + doc.label
          }
          onClick={() => onRetry(doc.type, doc.taskId)}
        >
          {running
            ? "正在下载…"
            : doc.status === "archived"
              ? "重新下载"
              : doc.status === "failed"
                ? "重试下载"
                : "立即下载"}
        </Button>
      </span>
      {!doc.retry.allowed && <span>{doc.retry.reason}</span>}
    </>
  );
}

function Files({ doc }: { doc: DeclarationDocument }) {
  return (
    <>
      {doc.archivedAt && <p>归档时间：{formatTime(doc.archivedAt)}</p>}
      {doc.attempts > 0 && <p>已尝试 {doc.attempts} 次</p>}
      {doc.files.map((file) => (
        <p key={file.path}>
          {file.filename}
          <br />
          保存路径：{file.path}
        </p>
      ))}
    </>
  );
}
