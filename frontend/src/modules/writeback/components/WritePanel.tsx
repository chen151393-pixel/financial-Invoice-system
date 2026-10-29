import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  Dialog,
} from "../../../shared/components/ui";
import type { TaskDetail } from "../types";

// 回写预览与写入：金额全部展示后端字符串；能否确认、能否写入以后端 actions 为准，点击后后端仍会重新校验。
export function WritePanel({
  task,
  busy,
  writing = false,
  unverified = false,
  onConfirmPreview,
  onExecute,
}: {
  task: TaskDetail;
  busy: boolean;
  writing?: boolean;
  unverified?: boolean;
  onConfirmPreview: () => void;
  onExecute: () => void;
}) {
  const [checked, setChecked] = useState(false);
  const [asking, setAsking] = useState(false);
  const request = task.request;
  if (!request) return null;
  const { invoice } = request;
  const executing = writing || task.state === "executing" || request.state === "executing";
  return (
    <Card>
      <CardHeader
        title="NS 回写预览"
        description={`发票 ${invoice.number} · 开票日期 ${invoice.date} · 含税 ${invoice.amount} 元 · 账单 ${request.preview.length} 张`}
        actions={
          task.actions.execute || executing ? (
            <Button
              variant="primary"
              disabled={busy || executing || unverified}
              aria-busy={executing}
              onClick={() => setAsking(true)}
            >
              {executing ? "正在回写…" : unverified ? "回写结果待核实" : "回写到 NS"}
            </Button>
          ) : undefined
        }
      />
      <DataTable
        label="回写预览"
        rows={request.preview}
        rowKey={(row) => row.billId}
        minWidth={760}
        columns={[
          { key: "bill", header: "账单", render: (row) => row.billNumber },
          { key: "parent", header: "母采购 ID", render: (row) => row.purchaseOrderId },
          { key: "before", header: "写前累计（元）", align: "right", render: (row) => row.before },
          { key: "amount", header: "本次金额（元）", align: "right", render: (row) => row.amount },
          { key: "after", header: "写后累计（元）", align: "right", render: (row) => row.after },
          { key: "details", header: "明细合计（元）", align: "right", render: (row) => row.detailsTotal },
          {
            key: "consistent",
            header: "累计与明细",
            render: (row) =>
              row.consistent ? (
                <Badge tone="success">一致</Badge>
              ) : (
                <Badge tone="warning">不一致，差额 {row.difference} 元</Badge>
              ),
          },
        ]}
      />
      <CardContent>
        {request.needsConfirmation && (
          <Alert tone="warning" title="账单累计与明细合计不一致">
            写后累计按“写前累计＋本次金额”计算，原有差额保持不变，不会被本次回写修正。
            {request.confirmedBy
              ? ` 已由 ${request.confirmedBy} 于 ${request.confirmedAt} 确认预览。`
              : " 请核对后确认预览，确认前不会写入 NS。"}
          </Alert>
        )}
        {task.actions.confirmPreview && (
          <div className="wb-plan-fields">
            <label className="wb-check">
              <input
                type="checkbox"
                checked={checked}
                disabled={busy}
                onChange={(event) => setChecked(event.target.checked)}
              />
              已核对上表每张账单的写前累计、本次金额和写后累计
            </label>
            <div>
              <Button variant="primary" disabled={busy || !checked} onClick={onConfirmPreview}>
                确认回写预览
              </Button>
            </div>
          </div>
        )}
        {task.state === "ready" && !task.actions.execute && (
          <p className="wb-secondary">暂不能写入：{task.writeback.reason}</p>
        )}
        {request.nsRecordId && (
          <p className="wb-secondary">
            NS 供应商发票记录 ID：{request.nsRecordId}
            {request.finishedAt ? ` · 完成于 ${request.finishedAt}` : ""}
          </p>
        )}
      </CardContent>
      {asking && (
        <Dialog title="确认回写到 NS" busy={busy || executing} onClose={() => setAsking(false)}>
          <p>
            将在 NS 新建发票 {invoice.number} 的供应商发票记录及 {request.preview.length}{" "}
            行明细，并更新上表账单的累计已收发票金额。
          </p>
          <p className="wb-secondary">
            写入后本系统不会自动撤回；如需更正，须由财务在 NS 处理。若结果不明，任务会停在“结果不明”，须在 NS
            核实后标记，不会自动重发。
          </p>
          <div className="wb-dialog-actions">
            <Button disabled={busy || executing} onClick={() => setAsking(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={busy || executing}
              onClick={() => {
                if (busy || executing) return;
                setAsking(false);
                onExecute();
              }}
            >
              {executing ? "正在回写…" : "确认回写"}
            </Button>
          </div>
        </Dialog>
      )}
    </Card>
  );
}
