import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  EmptyState,
  MetricCard,
  MetricGrid,
} from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { TaskDetail } from "../types/task";
import "./task-materials.css";
import "./task-receipts.css";

function amount(value: string | null | undefined, currency: string) {
  return value == null || value === "" ? "金额待确认" : `${money(value)} ${currency || "币种待核实"}`;
}

/** 发票比对节点的收票概况；汇总与各原任务金额直接来自后端，不在浏览器反算。 */
export function TaskReceiptCard({
  detail,
  onNotification,
}: {
  detail: TaskDetail;
  onNotification: () => void;
}) {
  const task = detail.task;
  const rows = detail.grouped ? detail.memberTasks || [] : [task];
  return (
    <Card className="it-receipts" aria-labelledby="it-receipts-title">
      <CardHeader
        title={<span id="it-receipts-title">收票概况</span>}
        actions={
          <Button size="sm" onClick={onNotification}>
            查看通知与催票
          </Button>
        }
      />
      <CardContent>
        <div className="it-receipts__content">
          <div className="it-receipts__metrics">
            <MetricGrid label="收票金额">
              <MetricCard label="应开合计" value={amount(task.expectedAmount, task.currency)} />
              <MetricCard label="已收金额" value={amount(task.receivedAmount, task.currency)} />
              <MetricCard label="待收金额" value={amount(task.outstandingAmount, task.currency)} />
            </MetricGrid>
          </div>
          {rows.length ? (
            <DataTable
              label="各报关单收票进度"
              rows={rows}
              rowKey={(row) => row.id}
              minWidth={620}
              density="compact"
              columns={[
                {
                  key: "document",
                  header: "报关单 / 子采购",
                  width: "42%",
                  render: (row) => (
                    <div className="it-materials__file">
                      <strong>{row.recordNumber || "CD 号待补充"}</strong>
                      <span>
                        {row.orderNumbers.length ? row.orderNumbers.join("、") : "子采购单号待补充"}
                      </span>
                    </div>
                  ),
                },
                {
                  key: "expected",
                  header: "应开含税金额",
                  align: "right",
                  render: (row) => amount(row.expectedAmount, row.currency),
                },
                {
                  key: "received",
                  header: "已收金额",
                  align: "right",
                  render: (row) => amount(row.receivedAmount, row.currency),
                },
                {
                  key: "status",
                  header: "任务状态",
                  render: (row) => <Badge>{row.statusLabel}</Badge>,
                },
              ]}
            />
          ) : (
            <EmptyState title="暂无报关单收票明细" description="请刷新任务详情，读取各原任务的收票进度。" />
          )}
          <p className="it-help">
            已收金额由发票比对中已通过的有效分配汇总；待收金额沿用任务行的实际未收口径，差异结束或超收时不按合计差额反算。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
