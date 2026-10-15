import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import { tierLabels, type Allocation, type ConfirmBody } from "../types/matching";
import { ChecksTable } from "./ChecksTable";

type Mode = "confirm" | "reject" | "cancel" | null;
const time = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }) : "";

export function AllocationCard({
  allocation,
  busy,
  onConfirm,
  onReject,
  onCancel,
}: {
  allocation: Allocation;
  busy: boolean;
  onConfirm: (body: ConfirmBody) => void;
  onReject: (note: string) => void;
  onCancel: (reason: string) => void;
}) {
  const [mode, setMode] = useState<Mode>(null);
  const [note, setNote] = useState("");
  const [closes, setCloses] = useState(false);
  const purchase = allocation.purchase;
  const noteRequired = allocation.noteReasons.length > 0 || closes;
  return (
    <article
      className="matching-card"
      data-status={allocation.status}
      aria-label={`比对记录 ${allocation.id}`}
    >
      <div className="matching-heading">
        <div className="matching-row">
          <strong>{allocation.statusLabel}</strong>
          <span className="matching-badge" data-tier={allocation.tier}>
            置信度 {allocation.confidence ?? "—"} · {tierLabels[allocation.tier]}
          </span>
          {allocation.exceedsExpected && <span className="matching-badge matching-warning">超开</span>}
          {allocation.closesPurchaseLine && <span className="matching-badge">按差异结束</span>}
        </div>
        <span>
          分配 {allocation.quantity} · 含税 {allocation.amount}
        </span>
      </div>
      {purchase && (
        <dl className="matching-facts">
          <div>
            <dt>子采购单 / 报关单</dt>
            <dd>
              {purchase.orderNo || "—"} · {purchase.recordNumber || "无有效任务"}
            </dd>
          </div>
          <div>
            <dt>供应商 / 采购公司</dt>
            <dd>
              {purchase.supplier || "—"} · {purchase.company || "—"}
            </dd>
          </div>
          <div>
            <dt>品名 / 单位</dt>
            <dd>
              {purchase.item || "—"} · {purchase.unit || "单位缺失"}
            </dd>
          </div>
          <div>
            <dt>剩余应开（数量 / 含税）</dt>
            <dd>
              {purchase.remainingQuantity ?? "—"} / {purchase.remainingAmount ?? "金额缺失"}
            </dd>
          </div>
          <div>
            <dt>子采购币种</dt>
            <dd>
              {purchase.currency || "待核实"} {purchase.currencyNote && `（${purchase.currencyNote}）`}
            </dd>
          </div>
        </dl>
      )}
      <details>
        <summary>逐项比对</summary>
        <ChecksTable checks={allocation.checks} caption="发票行与子采购行逐项比对" />
      </details>
      {allocation.reviewedBy && (
        <p className="matching-help">
          审核：{allocation.reviewedBy} · {time(allocation.reviewedAt)}
          {allocation.reviewNote && ` · 说明：${allocation.reviewNote}`}
        </p>
      )}
      {allocation.cancelledBy && (
        <p className="matching-help">
          取消：{allocation.cancelledBy} · {time(allocation.cancelledAt)} · {allocation.cancelReason}
        </p>
      )}
      {allocation.status === "proposed" && (
        <>
          {allocation.noteReasons.length > 0 && (
            <ul className="matching-reasons" aria-label="通过时需填写说明的原因">
              {allocation.noteReasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          )}
          <p className="matching-help">{allocation.confirm.reason}</p>
        </>
      )}
      {mode === null ? (
        <div className="matching-row">
          {allocation.status === "proposed" && (
            <>
              <Button
                variant="primary"
                disabled={busy || !allocation.confirm.allowed}
                onClick={() => setMode("confirm")}
              >
                通过
              </Button>
              <Button disabled={busy || !allocation.reject.allowed} onClick={() => setMode("reject")}>
                驳回
              </Button>
            </>
          )}
          {allocation.status === "confirmed" && (
            <Button disabled={busy || !allocation.cancel.allowed} onClick={() => setMode("cancel")}>
              取消分配
            </Button>
          )}
        </div>
      ) : (
        <form
          className="matching-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (mode === "confirm") onConfirm({ note, closesPurchaseLine: closes });
            else if (mode === "reject") onReject(note);
            else onCancel(note);
          }}
        >
          {mode === "confirm" && (
            <label className="matching-check">
              <input
                type="checkbox"
                checked={closes}
                disabled={busy}
                onChange={(e) => setCloses(e.target.checked)}
              />
              该子采购行已开完（金额有差异也按已开完结束）
            </label>
          )}
          <label>
            {mode === "cancel"
              ? "取消原因（必填）"
              : mode === "confirm" && noteRequired
                ? "审核说明（必填）"
                : "说明（选填）"}
            <textarea
              rows={2}
              maxLength={300}
              value={note}
              disabled={busy}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>
          <div className="matching-row">
            <Button type="submit" variant="primary" disabled={busy}>
              {busy
                ? "提交中…"
                : mode === "confirm"
                  ? "确认通过"
                  : mode === "reject"
                    ? "确认驳回"
                    : "确认取消"}
            </Button>
            <Button disabled={busy} onClick={() => setMode(null)}>
              返回
            </Button>
          </div>
        </form>
      )}
    </article>
  );
}
