import { useState } from "react";
import { Badge, Button, Card, CardContent, CardHeader, ProgressRing } from "../../../shared/components/ui";
import {
  tierLabels,
  type Allocation,
  type ConfirmBody,
  type InvoiceMatching,
  type InvoiceItem,
} from "../types/matching";
import { ComparisonSummary } from "./ComparisonSummary";
import { ChecksTable } from "./ChecksTable";

type Mode = "confirm" | "reject" | "cancel" | "reverify" | null;
const time = (value: string | null) =>
  value ? new Date(value).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" }) : "";

export function AllocationCard({
  allocation,
  busy,
  onConfirm,
  onReverify,
  onReject,
  onCancel,
  invoice,
  item,
  readOnly = false,
}: {
  allocation: Allocation;
  busy: boolean;
  onConfirm: (body: ConfirmBody) => void;
  onReverify?: (body: ConfirmBody) => void;
  onReject: (note: string) => void;
  onCancel: (reason: string) => void;
  invoice?: InvoiceMatching["invoice"];
  item?: InvoiceItem;
  readOnly?: boolean;
}) {
  const [mode, setMode] = useState<Mode>(null);
  const [note, setNote] = useState("");
  const purchase = allocation.purchase;
  const noteRequired = allocation.noteReasons.length > 0 || mode === "reverify";
  return (
    <Card
      className="matching-comparison"
      data-status={allocation.status}
      aria-label={`比对记录 ${allocation.id}`}
    >
      <CardHeader
        title={`${purchase?.supplier || "子采购比对"} · ${purchase?.orderNo || "—"}`}
        description={
          <span className="matching-row">
            <Badge tone="info">{allocation.statusLabel}</Badge>
            {allocation.exceedsExpected && <Badge tone="warning">超开</Badge>}
            {allocation.closesPurchaseLine && <Badge>按差异结束</Badge>}
            <span>
              第 {item?.lineNo || "—"} 行 · 发票数量 {allocation.quantity} · 采购数量{" "}
              {allocation.purchaseQuantity ?? "待核实"} · 含税 {allocation.amount}
            </span>
          </span>
        }
        actions={
          <div className="matching-confidence">
            {allocation.confidence !== null && (
              <ProgressRing
                value={allocation.confidence}
                text={`${allocation.confidence}%`}
                label="匹配置信度"
              />
            )}
            <span>
              <small>匹配置信度</small>
              <strong>{tierLabels[allocation.tier]}置信度</strong>
            </span>
          </div>
        }
      />
      <CardContent className="matching-comparison-content">
        {invoice && item ? (
          <ComparisonSummary invoice={invoice} item={item} purchase={purchase} />
        ) : (
          purchase && (
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
          )
        )}
        {allocation.verificationIssues?.length > 0 && (
          <ul className="matching-reasons" aria-label="待复核原因">
            {allocation.verificationIssues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        )}
        <ChecksTable checks={allocation.checks} caption="发票行与子采购行逐项比对" />
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
        {allocation.status === "confirmed" && allocation.verificationStatus !== "valid" && (
          <p className="matching-help">{allocation.reverify.reason}</p>
        )}
        {!readOnly &&
          (mode === null ? (
            <div className="matching-row matching-review-actions">
              {allocation.status === "proposed" && (
                <>
                  <Button
                    variant="primary"
                    disabled={busy || !allocation.confirm.allowed}
                    onClick={() => setMode("confirm")}
                  >
                    确认通过
                  </Button>
                  <Button disabled={busy || !allocation.reject.allowed} onClick={() => setMode("reject")}>
                    驳回
                  </Button>
                </>
              )}
              {onReverify &&
                allocation.status === "confirmed" &&
                allocation.verificationStatus !== "valid" && (
                  <Button
                    disabled={busy || !allocation.reverify.allowed}
                    title={allocation.reverify.reason}
                    onClick={() => setMode("reverify")}
                  >
                    重新核实分配
                  </Button>
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
                const body = {
                  note,
                  invoiceVersionId: allocation.currentInvoiceVersionId,
                  purchaseBasisId: purchase?.purchaseBasisId,
                };
                if (mode === "confirm") onConfirm(body);
                else if (mode === "reverify") onReverify?.(body);
                else if (mode === "reject") onReject(note);
                else onCancel(note);
              }}
            >
              <label>
                {mode === "cancel"
                  ? "取消原因（必填）"
                  : (mode === "confirm" || mode === "reverify") && noteRequired
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
                    : mode === "reverify"
                      ? "确认重新核实"
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
          ))}
      </CardContent>
    </Card>
  );
}
