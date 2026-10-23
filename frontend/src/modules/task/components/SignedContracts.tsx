import { Button } from "../../../shared/components/Button";
import type { SignedContract } from "../types/task";
import { formatTime } from "./format";

/** 回签合同：每张子采购单一份，人工上传；不阻塞通知与收票，到齐后任务才完结。 */
export function SignedContracts({
  contracts,
  disabled,
  onUpload,
}: {
  contracts: SignedContract[];
  disabled: boolean;
  onUpload: () => void;
}) {
  return (
    <div>
      <div className="itd-section-heading">
        <h3>回签合同</h3>
        <Button disabled={disabled} onClick={onUpload}>
          上传回签合同
        </Button>
      </div>
      <p className="it-help">
        按文件名中的子采购单号自动归入对应报关单文件夹；识别不了的可在上传结果中指定单号。
      </p>
      {contracts.length === 0 && <p>此任务没有子采购订单。</p>}
      {contracts.map((contract) => (
        <div key={contract.orderId} className="itd-document">
          <span className="itd-file-type" aria-hidden="true">
            回签
          </span>
          <div className="itd-document__info">
            <strong>{contract.orderNumber || "子采购单编号缺失"}</strong>
            <p>
              {contract.uploaded
                ? `已上传 · ${contract.uploadedBy} · ${formatTime(contract.uploadedAt!)}`
                : "尚未上传"}
            </p>
            {contract.archivePath && <p className="it-reference">保存路径：{contract.archivePath}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}
