import { Badge, Button, DataTable, EmptyState, Icon } from "../../../shared/components/ui";
import type { SignedContract } from "../types/task";
import { formatTime } from "./format";
import "./task-materials.css";

/** 回签合同默认折叠；统计由后端返回，展开后仍可逐单核查并上传。 */
export function SignedContracts({
  contracts,
  disabled,
  onUpload,
  summary,
  pendingCount,
}: {
  contracts: SignedContract[];
  disabled: boolean;
  onUpload: () => void;
  summary?: string;
  pendingCount?: number;
}) {
  return (
    <details className="it-materials it-materials__signed">
      <summary>
        <strong>回签合同</strong>
        <Badge
          tone={
            pendingCount === undefined || !contracts.length
              ? "neutral"
              : pendingCount > 0
                ? "warning"
                : "success"
          }
        >
          {summary || "回签状态待获取"}
        </Badge>
        <span className="it-help">展开查看子采购单</span>
        <span className="it-materials__chevron">
          <Icon name="chevronRight" />
        </span>
      </summary>
      <div className="it-materials__section">
        <div className="it-materials__heading">
          <Button size="sm" disabled={disabled} onClick={onUpload}>
            上传回签合同
          </Button>
          <span className="it-help">按子采购单号归档，无法识别时可在上传结果中指定。</span>
        </div>
        {contracts.length ? (
          <DataTable
            label="回签合同清单"
            rows={contracts}
            rowKey={(contract) => contract.orderId}
            minWidth={560}
            density="compact"
            columns={[
              {
                key: "order",
                header: "子采购单",
                render: (contract) => <strong>{contract.orderNumber || "单号缺失"}</strong>,
              },
              {
                key: "status",
                header: "回签状态",
                render: (contract) => (
                  <Badge tone={contract.uploaded ? "success" : "warning"}>
                    {contract.uploaded ? "已上传" : "尚未上传"}
                  </Badge>
                ),
              },
              {
                key: "file",
                header: "文件与归档信息",
                render: (contract) => (
                  <div className="it-materials__file">
                    <span>{contract.filename || "尚无回签文件"}</span>
                    {contract.uploadedAt && (
                      <span>
                        {contract.uploadedBy} · {formatTime(contract.uploadedAt)}
                      </span>
                    )}
                    {contract.archivePath && (
                      <details>
                        <summary>归档位置</summary>
                        <p>{contract.archivePath}</p>
                      </details>
                    )}
                  </div>
                ),
              },
            ]}
          />
        ) : (
          <EmptyState title="暂无回签合同" description="此任务没有子采购订单。" />
        )}
      </div>
    </details>
  );
}
