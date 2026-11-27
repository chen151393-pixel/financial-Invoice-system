import { Alert, Badge, DataTable, EmptyState } from "../../../shared/components/ui";
import type { TaskDetail } from "../types/task";
import "./task-materials.css";

/** 每张报关单各自的审核版本与通过事实，保留合并前的依据。 */
export function TaskReview({ detail }: { detail: TaskDetail }) {
  const rows = detail.reviewRows || [];
  return (
    <div className="it-materials">
      <p className="it-help">以下为任务生成时已通过的海关与财务审核依据，合并后继续保留各自的审核版本。</p>
      {!detail.compare.allowed && (
        <Alert tone="warning" title="审核依据需核实">
          {detail.sourceMessage}
        </Alert>
      )}
      {rows.length ? (
        <DataTable
          label="报关单审核依据"
          rows={rows}
          rowKey={(row) => row.taskId}
          minWidth={600}
          density="compact"
          columns={[
            {
              key: "record",
              header: "报关单",
              render: (row) => (
                <div className="it-materials__file">
                  <strong>{row.recordNumber || "CD 号缺失"}</strong>
                  <span>{row.declarationNumber || "真实报关单号待补充"}</span>
                </div>
              ),
            },
            {
              key: "customs",
              header: "海关审核",
              render: (row) => <Badge tone="success">{row.customsStatusLabel}</Badge>,
            },
            {
              key: "finance",
              header: "财务审核",
              render: (row) => (
                <div className="it-materials__file">
                  <span>
                    <Badge tone="success">{row.financeStatusLabel}</Badge>
                  </span>
                  <span>审核版本 {row.reviewRevision}</span>
                </div>
              ),
            },
            { key: "orders", header: "子采购单", render: (row) => `${row.orderCount} 张` },
          ]}
        />
      ) : (
        <EmptyState title="审核依据待获取" description="请刷新任务详情，读取各报关单的审核记录。" />
      )}
    </div>
  );
}
