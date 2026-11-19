import { useState } from "react";
import { Alert, Badge, Button, DataTable, Dialog } from "../../../shared/components/ui";
import type { BoardItem, NotifyBatchResult } from "../types/board";

/**
 * 批量登记“线下已通知供应商”：确认本页勾选的任务并展示逐任务结果。
 * 只登记，不发送消息；发送时间由后端取登记当时。失败后先关闭刷新核实，不直接重发。
 */
export function NotifyBatchDialog({
  items,
  busy,
  result,
  error,
  onClose,
  onSubmit,
}: {
  items: BoardItem[];
  busy: boolean;
  result: NotifyBatchResult | null;
  error: string;
  onClose: () => void;
  onSubmit: (note: string) => void;
}) {
  const [note, setNote] = useState("");
  const done = !!result || !!error;
  return (
    <Dialog title={done ? "批量登记结果" : "批量登记已通知"} busy={busy} onClose={onClose}>
      <div className="tb-batch">
        <p className="tb-batch__help">
          用于已在系统外（企微群、电话等）通知供应商开票的任务。本页已选 {items.length}{" "}
          个任务，登记后进入“待供应商开票”；通知时间记为今天，系统不会发送任何消息。
        </p>
        {result && (
          <Alert tone={result.skipped.length ? "warning" : "success"}>
            已登记 {result.recorded.length} 个，跳过 {result.skipped.length} 个。
          </Alert>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <DataTable
          label="本次批量登记的任务"
          rows={items}
          rowKey={(item) => item.task.id}
          minWidth={560}
          maxHeight="46dvh"
          columns={[
            { key: "supplier", header: "供应商", render: (item) => item.task.supplier },
            { key: "record", header: "CD 号", render: (item) => item.task.recordNumber || "—" },
            {
              key: "orders",
              header: done ? "处理结果" : "子采购单",
              render: (item) => {
                if (!done) return item.task.orderNumbers.join("、") || "—";
                const skipped = result?.skipped.find((entry) => entry.id === item.task.id);
                if (skipped) return <span>{skipped.reason}</span>;
                if (result?.recorded.some((entry) => entry.id === item.task.id))
                  return <Badge tone="success">已登记</Badge>;
                return "结果待核实，请刷新查看";
              },
            },
          ]}
        />
        {!done && (
          <label className="tb-batch__note">
            登记说明（选填，应用于本次全部任务）
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              maxLength={300}
              rows={2}
              disabled={busy}
              placeholder="不填时记为“批量登记：线下已通知供应商开票”"
            />
          </label>
        )}
        {busy && <p role="status">正在逐个登记，请稍候…</p>}
        <div className="tb-batch__actions">
          <Button disabled={busy} onClick={onClose}>
            {done ? "关闭" : "取消"}
          </Button>
          {!done && (
            <Button variant="primary" disabled={busy || !items.length} onClick={() => onSubmit(note)}>
              {busy ? "登记中…" : `确认已通知 ${items.length} 个`}
            </Button>
          )}
        </div>
      </div>
    </Dialog>
  );
}
