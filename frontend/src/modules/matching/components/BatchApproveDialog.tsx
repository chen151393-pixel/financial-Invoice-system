import { useState } from "react";
import { Alert, Badge, Button, DataTable, Dialog } from "../../../shared/components/ui";
import type { InvoiceBatchResult, InvoiceQueueRow } from "../types/matching";

/** 当前页已选发票的确认与逐票结果，失败后先刷新核实，不直接重发。 */
export function BatchApproveDialog({
  rows,
  busy,
  result,
  error,
  onClose,
  onApprove,
}: {
  rows: InvoiceQueueRow[];
  busy: boolean;
  result: InvoiceBatchResult | null;
  error: string;
  onClose: () => void;
  onApprove: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const done = !!result || !!error;
  return (
    <Dialog title={done ? "批量审核结果" : "批量审核通过"} busy={busy} onClose={onClose}>
      <div className="matching-batch">
        <p className="matching-help">
          当前页已选 {rows.length} 张发票，仅审核下列发票的全部待审核建议。后端逐张复核置信度必须为 100%，
          数据已变化或不符合条件的整张跳过。
        </p>
        {result && (
          <Alert tone={result.skipped.length ? "warning" : "success"}>
            已通过 {result.approved.length} 张，跳过 {result.skipped.length} 张。
          </Alert>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <DataTable
          label="本次批量审核发票"
          rows={rows}
          rowKey={(row) => row.invoice.id}
          minWidth={520}
          columns={[
            { key: "number", header: "发票号码", render: (row) => row.invoice.number },
            { key: "seller", header: "供应商", render: (row) => row.invoice.seller || "—" },
            {
              key: "result",
              header: done ? "处理结果" : "置信度",
              render: (row) => {
                if (!done) return `${row.confidence}%`;
                const skipped = result?.skipped.find((item) => item.id === row.invoice.id);
                if (skipped) return <span>{skipped.reason}</span>;
                if (result?.approved.some((item) => item.id === row.invoice.id))
                  return <Badge tone="success">已审核通过</Badge>;
                return "结果待核实，请刷新查看";
              },
            },
          ]}
        />
        {!done && (
          <label className="matching-form">
            审核备注（选填，应用于本次全部发票）
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={300}
              rows={3}
              disabled={busy}
            />
          </label>
        )}
        {busy && <p role="status">正在逐张保存审核结果，请稍候…</p>}
        <div className="matching-row matching-batch__actions">
          <Button disabled={busy} onClick={onClose}>
            {done ? "关闭" : "取消"}
          </Button>
          {!done && (
            <Button variant="primary" disabled={busy || !rows.length} onClick={() => onApprove(note)}>
              {busy ? "审核中…" : `审核通过 ${rows.length} 张`}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
