import { Badge } from "../../../shared/components/ui";
import type { DeclarationDocumentType, TaskDetail } from "../types/task";
import { DeclarationDocuments } from "./DeclarationDocuments";
import { PurchaseContracts } from "./PurchaseContracts";
import { SignedContracts } from "./SignedContracts";
import "./task-materials.css";

export function TaskDocuments({
  detail,
  busy,
  onPrepare,
  onRetryDeclaration,
  onUploadSigned,
}: {
  detail: TaskDetail;
  busy: string | null;
  onPrepare: (orderId: string) => void;
  onRetryDeclaration: (type: DeclarationDocumentType, taskId?: string) => void;
  onUploadSigned: () => void;
}) {
  const preparation = detail.preparation;
  return (
    <div className="it-materials">
      <section className="it-materials__section" aria-label="子采购合同">
        <div className="it-materials__heading">
          <h4>子采购合同</h4>
          <Badge tone={preparation?.contractsReady ? "success" : "warning"}>
            {preparation?.contractSummary || "归档数量待获取"}
          </Badge>
          <span className="it-help">生成通知时带入本次通知范围的全部合同</span>
        </div>
        <PurchaseContracts documents={detail.documents} busy={busy} onPrepare={onPrepare} pathOnly />
      </section>
      <DeclarationDocuments
        groups={detail.declarationRows || []}
        count={preparation?.declarationCount}
        busy={busy}
        onRetry={onRetryDeclaration}
      />
      <SignedContracts
        contracts={detail.signedContracts}
        summary={preparation?.signedSummary}
        pendingCount={preparation?.signedPendingCount}
        disabled={detail.sourceStatus === "superseded" || busy !== null}
        onUpload={onUploadSigned}
      />
      {detail.reasons.map((reason) => (
        <p className="it-help" key={reason}>
          {reason}
        </p>
      ))}
    </div>
  );
}
