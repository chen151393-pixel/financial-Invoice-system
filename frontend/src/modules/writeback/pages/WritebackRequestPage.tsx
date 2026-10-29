import { Link } from "react-router";
import { matchingInvoicePath } from "../../../app/paths";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  Skeleton,
} from "../../../shared/components/ui";
import { confirmPlan, confirmPreview, executeWrite, refreshTask, resolveWrite } from "../api";
import { PlanForm } from "../components/PlanForm";
import { ResolveForm } from "../components/ResolveForm";
import { WritePanel } from "../components/WritePanel";
import type { ConfirmBody, ResolveBody, TaskDetail } from "../types";
import { useWritebackRequest } from "../hooks/useWritebackRequest";
import "../writeback.css";

const actionLabels: Record<string, string> = {
  queued: "生成任务",
  invalidated: "审核失效",
  queried: "查询完成",
  query_failed: "查询失败",
  plan_confirmed: "确认方案",
  preview_confirmed: "确认回写预览",
  write_started: "开始写入 NS",
  write_finished: "写入结束",
  write_resolved: "人工核实写入结果",
  changed_after_write: "写入后审核变化",
};
export function TaskContent({
  task,
  busy,
  writing = false,
  unverified = false,
  onRefresh,
  onConfirm,
  onConfirmPreview,
  onExecute,
  onResolve,
}: {
  task: TaskDetail;
  busy: boolean;
  writing?: boolean;
  unverified?: boolean;
  onRefresh: () => void;
  onConfirm: (body: ConfirmBody) => void;
  onConfirmPreview: () => void;
  onExecute: () => void;
  onResolve: (body: ResolveBody) => void;
}) {
  const bills = task.candidates?.purchaseOrders.flatMap((order) => order.bills) ?? [];
  return (
    <>
      <Alert title={writing ? "正在回写 NS" : unverified ? "回写结果待核实" : task.stateLabel}>
        {writing
          ? "正在提交回写请求并等待 NS 处理结果，请勿重复提交。"
          : unverified
            ? "请先刷新任务状态，取得最新结果后再处理；不要重复提交回写。"
            : task.reason}
      </Alert>
      <Card>
        <CardHeader
          title={`发票 ${task.invoiceNo}`}
          description={`${task.vendorName} · 含税 ${task.amount} 元${task.historical ? " · 历史发票，须人工核实" : ""}`}
          actions={
            <>
              <Link to={matchingInvoicePath(task.invoiceId)}>查看匹配审核</Link>
              <Button disabled={busy || !task.actions.refresh} onClick={onRefresh}>
                {task.querying ? "正在查询" : "重新查询账单"}
              </Button>
            </>
          }
        />
        <DataTable
          label="已审核子采购单"
          rows={task.orders}
          rowKey={(row) => row.subPurchaseOrderId}
          minWidth={580}
          columns={[
            { key: "subpo", header: "子采购", render: (row) => row.orderNo },
            { key: "parent", header: "母采购", render: (row) => row.parentOrderNo },
            {
              key: "lines",
              header: "商品明细",
              render: (row) => (
                <details>
                  <summary>{row.lineCount} 条明细</summary>
                  <ul>
                    {row.allocations.map((line) => (
                      <li key={line.allocationId}>
                        采购行 {line.purchaseLineId} · 分配 {line.allocationId} · {line.amount} 元
                      </li>
                    ))}
                  </ul>
                </details>
              ),
            },
            { key: "amount", header: "含税金额（元）", align: "right", render: (row) => row.amount },
          ]}
        />
      </Card>
      <Card>
        <CardHeader
          title="NS 候选账单"
          description={
            task.candidates
              ? `读取完成：${task.candidates.readCompletedAt}；该额度仅为查询结果，尚未预留。`
              : "先查询账单，再确认归属和金额。"
          }
        />
        {bills.length ? (
          <DataTable
            label="候选账单"
            rows={bills}
            rowKey={(row) => row.billId}
            columns={[
              { key: "bill", header: "账单", render: (row) => row.billNumber },
              { key: "parent", header: "母采购 ID", render: (row) => row.purchaseOrderId },
              { key: "subpo", header: "子采购 ID", render: (row) => row.subPurchaseOrderId || "未明确关联" },
              { key: "company", header: "实际子公司 ID", render: (row) => row.subsidiaryId },
              {
                key: "available",
                header: "可收金额",
                align: "right",
                render: (row) => `${row.availableInvoiceAmount} ${row.currency}`,
              },
              { key: "issues", header: "核实事项", render: (row) => row.issues.join("；") || "归属仍需核实" },
            ]}
          />
        ) : (
          <EmptyState
            title={task.candidates ? "未取得可用账单" : "尚未查询账单"}
            description={
              task.candidates?.purchaseOrders.map((order) => order.reason).join("；") || task.reason
            }
          />
        )}
      </Card>
      {task.actions.confirm && <PlanForm key={task.revision} task={task} busy={busy} onConfirm={onConfirm} />}
      {task.plan && (
        <Card>
          <CardHeader
            title={task.state === "stale" ? "历史冻结方案（当前不可用）" : "已冻结方案"}
            description={`${task.plan.confirmedBy} · ${task.plan.confirmedAt}`}
          />
          <DataTable
            label="冻结方案"
            rows={task.plan.orders}
            rowKey={(row) => `${row.subPurchaseOrderId}-${row.billId}`}
            minWidth={480}
            columns={[
              { key: "order", header: "子采购单", render: (row) => row.orderNo },
              { key: "bill", header: "账单 ID", render: (row) => row.billId },
              { key: "amount", header: "金额（元）", align: "right", render: (row) => row.amount },
            ]}
          />
          <CardContent>{task.plan.evidence}</CardContent>
        </Card>
      )}
      <WritePanel
        key={`write-${task.revision}`}
        task={task}
        busy={busy}
        writing={writing}
        unverified={unverified}
        onConfirmPreview={onConfirmPreview}
        onExecute={onExecute}
      />
      {task.actions.resolve && (
        <ResolveForm key={`resolve-${task.revision}`} task={task} busy={busy} onResolve={onResolve} />
      )}
      <Card>
        <CardHeader title="处理记录" />
        <CardContent>
          <ol className="wb-audit">
            {task.audit.map((item, index) => (
              <li key={`${item.at}-${index}`}>
                <strong>{actionLabels[item.action] || "任务处理"}</strong> · {item.actor}
                <small className="wb-secondary">
                  {item.at} {item.detail.reason || item.detail.evidence}
                </small>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </>
  );
}

export function WritebackRequestPage({ requestId }: { requestId: string }) {
  const { task, error, busy, writing, unverified, run, refresh } = useWritebackRequest(requestId);
  return (
    <div className="wb-prepare">
      <div>
        <Button disabled={busy} onClick={refresh}>
          刷新任务状态
        </Button>
      </div>
      {error && (
        <ErrorState
          title="操作未完成"
          message={error}
          action={
            <Button disabled={busy} onClick={refresh}>
              重新加载
            </Button>
          }
        />
      )}
      {task && task.id === requestId ? (
        <TaskContent
          task={task}
          busy={busy || unverified}
          writing={writing}
          unverified={unverified}
          onRefresh={() => void run(() => refreshTask(requestId, task.revision))}
          onConfirm={(body) => void run(() => confirmPlan(requestId, body))}
          onConfirmPreview={() => void run(() => confirmPreview(requestId, task.revision))}
          onExecute={() => void run(() => executeWrite(requestId, task.revision), true)}
          onResolve={(body) => void run(() => resolveWrite(requestId, body))}
        />
      ) : (
        !error && <Skeleton label="正在加载回写任务" />
      )}
    </div>
  );
}
