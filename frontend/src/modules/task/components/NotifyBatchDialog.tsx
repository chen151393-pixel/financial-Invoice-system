import { useState } from "react";
import { Alert, Badge, Button, DataTable, Dialog, Field } from "../../../shared/components/ui";
import type { NotifyBatchGroup, NotifyGroupBatchResult } from "../types/board";

/**
 * 批量登记“线下已通知供应商”：确认本页选中组，后端逐组事务提交并返回结果。
 * 只登记，不发送消息；通知日期由后端校验保存。失败后先关闭刷新核实，不直接重发。
 */
export function NotifyBatchDialog({
  items,
  busy,
  result,
  error,
  onClose,
  onSubmit,
}: {
  items: NotifyBatchGroup[];
  busy: boolean;
  result: NotifyGroupBatchResult | null;
  error: string;
  onClose: () => void;
  onSubmit: (note: string, notifiedOn: string) => void;
}) {
  const [note, setNote] = useState("");
  const [defaultNotifiedOn] = useState(() =>
    new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(new Date()),
  );
  const done = !!result || !!error;
  const taskCount = items.reduce((count, item) => count + item.targets.length, 0);
  return (
    <Dialog title={done ? "批量登记结果" : "批量登记已通知"} busy={busy} onClose={onClose}>
      <form
        className="tb-batch"
        onSubmit={(event) => {
          event.preventDefault();
          const notifiedOn = new FormData(event.currentTarget).get("notifiedOn");
          if (!busy && !done && typeof notifiedOn === "string") onSubmit(note, notifiedOn);
        }}
      >
        <p className="tb-batch__help">
          用于已在系统外（企微群、电话等）通知供应商开票的任务。本页已选 {items.length} 组、{taskCount}{" "}
          个待通知任务。系统不会发送任何消息。已通知任务不在本次范围。
          系统按组处理，一组内全部成功才保存；范围变化时跳过整组，请刷新后重新确认。
        </p>
        {!done && (
          <Field label="通知日期（北京时间）">
            <input type="date" name="notifiedOn" defaultValue={defaultNotifiedOn} required disabled={busy} />
          </Field>
        )}
        {result && (
          <Alert tone={result.skippedGroups || result.unknownGroups ? "warning" : "success"}>
            {`已登记 ${result.recordedGroups} 组（${result.recordedTasks} 个任务），跳过 ${result.skippedGroups} 组，待核实 ${result.unknownGroups} 组。`}
          </Alert>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <DataTable
          label="本次批量登记的任务"
          rows={items}
          rowKey={(item) => item.id}
          minWidth={560}
          maxHeight="46dvh"
          columns={[
            { key: "supplier", header: "供应商", render: (item) => item.targets[0]?.supplier || "—" },
            {
              key: "record",
              header: "本组 CD 号",
              render: (item) => item.targets.map((target) => target.recordNumber || "—").join("、"),
            },
            {
              key: "orders",
              header: done ? "处理结果" : "子采购单",
              render: (item) => {
                if (!done) return item.targets.flatMap((target) => target.orderNumbers).join("、") || "—";
                const outcome = result?.groups.find((entry) => entry.id === item.id);
                if (outcome)
                  return (
                    <span>
                      <Badge tone={outcome.status === "recorded" ? "success" : "warning"}>
                        {outcome.status === "recorded"
                          ? "整组已登记"
                          : outcome.status === "skipped"
                            ? "整组跳过"
                            : "结果待核实"}
                      </Badge>{" "}
                      {outcome.reason}
                    </span>
                  );
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
        {busy && <p role="status">正在逐组登记，请稍候…</p>}
        <div className="tb-batch__actions">
          <Button disabled={busy} onClick={onClose}>
            {done ? "关闭" : "取消"}
          </Button>
          {!done && (
            <Button type="submit" variant="primary" disabled={busy || !items.length}>
              {busy ? "登记中…" : `确认已通知 ${items.length} 组（${taskCount} 个任务）`}
            </Button>
          )}
        </div>
      </form>
    </Dialog>
  );
}
