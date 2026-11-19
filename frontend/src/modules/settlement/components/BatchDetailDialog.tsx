import { useEffect, useState } from "react";
import { Alert, Badge, Button, DataTable, Dialog, ErrorState, Skeleton } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import { cancelBatch, getBatch, markDocumentsReady, recordRemittance, settleBatch } from "../api";
import type { BatchDetail, BatchItem } from "../types";
import { BatchDocuments } from "./BatchDocuments";

type State = { kind: "loading" } | { kind: "ready"; batch: BatchDetail } | { kind: "error"; message: string };

const ITEM_COLUMNS = [
  { key: "no", header: "报关单号", render: (row: BatchItem) => row.declarationNo },
  { key: "cd", header: "CD", render: (row: BatchItem) => row.recordNo || "—" },
  { key: "orders", header: "销售订单", render: (row: BatchItem) => row.salesOrders || "—" },
  { key: "date", header: "出口日期", render: (row: BatchItem) => row.exportDate || "—" },
  {
    key: "amount",
    header: "报关金额",
    align: "right" as const,
    render: (row: BatchItem) => `${row.currency} ${money(row.amount)}`,
  },
];

/** 批次详情：到账 / 汇回核对结果与可执行操作均来自后端，点击后后端再次校验。 */
export function BatchDetailDialog({
  batchId,
  onClose,
  onChanged,
}: {
  batchId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"none" | "remit" | "cancel">("none");

  useEffect(() => {
    const controller = new AbortController();
    getBatch(batchId, controller.signal)
      .then((batch) => setState({ kind: "ready", batch }))
      .catch((reason: unknown) => {
        if (reason instanceof Error && reason.name === "AbortError") return;
        setState({ kind: "error", message: reason instanceof Error ? reason.message : "加载失败" });
      });
    return () => controller.abort();
  }, [batchId]);

  async function run(action: () => Promise<BatchDetail>) {
    setBusy(true);
    setError("");
    try {
      const batch = await action();
      setState({ kind: "ready", batch });
      setMode("none");
      onChanged();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "操作失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  if (state.kind !== "ready") {
    return (
      <Dialog title="结汇批次" onClose={onClose}>
        {state.kind === "loading" ? (
          <Skeleton rows={4} label="正在读取批次" />
        ) : (
          <ErrorState title="批次读取失败" message={state.message} />
        )}
      </Dialog>
    );
  }
  const batch = state.batch;
  const hk = batch.route === "hk_transit";
  return (
    <Dialog title={`结汇批次 ${batch.batchNo}`} onClose={onClose} busy={busy} className="settlement-dialog">
      <div className="settlement-detail">
        <div className="settlement-detail__head">
          <Badge tone={hk ? "info" : "neutral"}>{batch.routeLabel}</Badge>
          <Badge
            tone={
              batch.status === "settled" ? "success" : batch.status === "cancelled" ? "neutral" : "progress"
            }
          >
            {batch.statusLabel}
          </Badge>
          <span>
            {batch.consignee} · 报关合计 {batch.currency} {money(batch.declaredTotal)}
          </span>
        </div>
        <dl className="settlement-detail__facts">
          <dt>到账</dt>
          <dd>
            {batch.receivedOn} · {money(batch.receivedAmount)}（手续费 {money(batch.receivedFee)}）
            {batch.receivedReference && ` · ${batch.receivedReference}`}
          </dd>
          <dt>付款方 / 账户</dt>
          <dd>
            {batch.payer || "—"} / {batch.receivingAccount || "—"}
          </dd>
          {hk && (
            <>
              <dt>汇回境内</dt>
              <dd>
                {batch.remittedOn
                  ? `${batch.remittedOn} · ${money(batch.remittedAmount)}（手续费 ${money(batch.remittedFee)}）`
                  : "尚未登记"}
              </dd>
            </>
          )}
          <dt>经办</dt>
          <dd>
            {batch.createdBy}
            {batch.documentsReadyBy && ` · 资料已出：${batch.documentsReadyBy}`}
            {batch.settledBy && ` · 结汇确认：${batch.settledBy}`}
            {batch.cancelReason && ` · 作废原因：${batch.cancelReason}`}
          </dd>
        </dl>
        {batch.balances.map((balance) => (
          <Alert
            key={balance.stage}
            tone={balance.balanced ? (balance.warnings.length ? "warning" : "success") : "danger"}
            title={`${balance.label}核对：${balance.balanced ? "已对平" : `差额 ${balance.difference}`}`}
          >
            {balance.warnings.length ? balance.warnings.join("；") : "到账加手续费等于报关合计。"}
          </Alert>
        ))}
        <DataTable
          label="批次报关单"
          columns={ITEM_COLUMNS}
          rows={batch.items}
          rowKey={(row) => row.declarationNo}
          density="compact"
        />
        {hk && batch.status !== "cancelled" && (
          <BatchDocuments
            target={batch.id}
            onChanged={() => {
              // 资料变化会影响“确认资料已出”是否可用，重新读取批次
              getBatch(batch.id)
                .then((fresh) => setState({ kind: "ready", batch: fresh }))
                .catch(() => undefined);
            }}
          />
        )}
        {mode === "remit" && (
          <form
            className="settlement-form"
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              const value = (name: string) => String(data.get(name) || "").trim();
              void run(() =>
                recordRemittance(batch.id, {
                  remittedOn: value("remittedOn"),
                  remittedAmount: value("remittedAmount"),
                  remittedFee: value("remittedFee") || "0",
                  remittedReference: value("remittedReference"),
                }),
              );
            }}
          >
            <label>
              汇回日期
              <input name="remittedOn" type="date" required />
            </label>
            <label>
              境内到账金额
              <input name="remittedAmount" inputMode="decimal" required />
            </label>
            <label>
              汇回手续费
              <input name="remittedFee" inputMode="decimal" defaultValue="0" />
            </label>
            <label>
              汇回流水号
              <input name="remittedReference" maxLength={200} />
            </label>
            <div className="settlement-form__actions">
              <Button type="button" variant="ghost" onClick={() => setMode("none")} disabled={busy}>
                取消
              </Button>
              <Button type="submit" disabled={busy}>
                登记汇回并确认结汇
              </Button>
            </div>
          </form>
        )}
        {mode === "cancel" && (
          <form
            className="settlement-form"
            onSubmit={(event) => {
              event.preventDefault();
              const reason = String(new FormData(event.currentTarget).get("reason") || "").trim();
              void run(() => cancelBatch(batch.id, reason));
            }}
          >
            <label className="settlement-form__wide">
              作废原因（作废后报关单可重新建批次）
              <input name="reason" required maxLength={300} />
            </label>
            <div className="settlement-form__actions">
              <Button type="button" variant="ghost" onClick={() => setMode("none")} disabled={busy}>
                返回
              </Button>
              <Button type="submit" disabled={busy}>
                确认作废
              </Button>
            </div>
          </form>
        )}
        {error && (
          <Alert tone="danger" title="操作未完成">
            {error}
          </Alert>
        )}
        {mode === "none" && (
          <div className="settlement-form__actions">
            {hk && batch.status === "collected" && (
              <Button
                disabled={busy || !batch.actions.documentsReady.allowed}
                title={batch.actions.documentsReady.reason}
                onClick={() => void run(() => markDocumentsReady(batch.id))}
              >
                确认资料已出
              </Button>
            )}
            {hk && batch.status === "documents_ready" && (
              <Button
                disabled={busy || !batch.actions.settle.allowed}
                title={batch.actions.settle.reason}
                onClick={() => setMode("remit")}
              >
                登记汇回
              </Button>
            )}
            {!hk && batch.status === "collected" && (
              <Button
                disabled={busy || !batch.actions.settle.allowed}
                title={batch.actions.settle.reason}
                onClick={() => void run(() => settleBatch(batch.id))}
              >
                确认已结汇
              </Button>
            )}
            {batch.actions.cancel.allowed && (
              <Button variant="ghost" disabled={busy} onClick={() => setMode("cancel")}>
                作废批次
              </Button>
            )}
          </div>
        )}
        {mode === "none" &&
          !batch.actions.settle.allowed &&
          batch.status !== "settled" &&
          batch.status !== "cancelled" && (
            <p className="settlement-form__hint">
              {hk && batch.status === "collected"
                ? batch.actions.documentsReady.reason
                : batch.actions.settle.reason}
            </p>
          )}
      </div>
    </Dialog>
  );
}
