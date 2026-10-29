import { useState } from "react";
import { Button, DataTable } from "../../../shared/components/ui";
import type { InvoiceItem } from "../types/matching";
import type { ManualOrderBody, ManualOrderCandidate } from "../types/manual-order";
import { ChecksTable } from "./ChecksTable";

type Shares = Record<string, { quantity: string; amount: string }>;

/** 选中整张子采购单后逐条明细填写本票分配；默认取后端给出的剩余应开，合计与校验均由后端完成。 */
export function OrderShareForm({
  order,
  item,
  invoiceId,
  invoiceVersionId,
  replaceId,
  reason,
  busy,
  onCreate,
}: {
  order: ManualOrderCandidate;
  item: InvoiceItem;
  invoiceId: string;
  invoiceVersionId: string | null;
  replaceId: string;
  reason: string;
  busy: boolean;
  onCreate: (body: ManualOrderBody) => Promise<boolean>;
}) {
  const [shares, setShares] = useState<Shares>(() =>
    Object.fromEntries(
      order.lines.map((line) => [
        line.purchaseLineId,
        { quantity: line.remainingQuantity ?? "", amount: line.remainingAmount ?? "" },
      ]),
    ),
  );
  const [note, setNote] = useState("");
  // 同一次填写沿用同一请求标识：提交结果不明时重试不会重复分配。
  const [requestId] = useState(() => crypto.randomUUID());
  const change = (id: string, key: "quantity" | "amount", value: string) =>
    setShares((current) => ({ ...current, [id]: { ...current[id], [key]: value } }));
  return (
    <form
      className="matching-form matching-share-form"
      aria-label={`分配子采购单 ${order.orderNo}`}
      onSubmit={(event) => {
        event.preventDefault();
        void onCreate({
          requestId,
          invoiceId,
          invoiceItemId: item.id,
          purchaseOrderId: order.purchaseOrderId,
          invoiceVersionId,
          lines: order.lines.map((line) => ({
            purchaseLineId: line.purchaseLineId,
            ...shares[line.purchaseLineId],
          })),
          note,
          replaceAllocationId: replaceId || null,
          replaceReason: reason,
        });
      }}
    >
      <p className="matching-help">
        已选 {order.orderNo}（{order.supplier || "供应商未提供"}）共 {order.lines.length}{" "}
        行明细。整张子采购单为最小关联单位，全部明细一起保存；部分开票时改小对应明细，本票不开的明细数量和金额填
        0。
      </p>
      <DataTable
        label={`子采购单 ${order.orderNo} 明细与本票分配`}
        rows={order.lines}
        rowKey={(line) => line.purchaseLineId}
        density="compact"
        minWidth={720}
        maxHeight={360}
        columns={[
          {
            key: "item",
            header: "品名 / 规格",
            render: (line) => (
              <span className="matching-cell">
                {line.item || "—"}
                {line.specification && <small>{line.specification}</small>}
              </span>
            ),
          },
          { key: "unit", header: "单位", render: (line) => line.unit || "单位缺失" },
          {
            key: "remaining",
            header: "剩余应开数量 / 含税",
            align: "right",
            render: (line) => (
              <span className="matching-cell">
                <span>{line.remainingQuantity ?? "—"}</span>
                <strong>
                  {line.remainingAmount ?? "—"} {line.currency}
                </strong>
              </span>
            ),
          },
          {
            key: "quantity",
            header: "本票分配数量",
            align: "right",
            render: (line) => (
              <input
                className="matching-share-input"
                inputMode="decimal"
                aria-label={`${line.item || "明细"} 本票分配数量`}
                value={shares[line.purchaseLineId]?.quantity ?? ""}
                disabled={busy}
                onChange={(event) => change(line.purchaseLineId, "quantity", event.target.value)}
              />
            ),
          },
          {
            key: "amount",
            header: "本票分配含税金额",
            align: "right",
            render: (line) => (
              <input
                className="matching-share-input"
                inputMode="decimal"
                aria-label={`${line.item || "明细"} 本票分配含税金额`}
                value={shares[line.purchaseLineId]?.amount ?? ""}
                disabled={busy}
                onChange={(event) => change(line.purchaseLineId, "amount", event.target.value)}
              />
            ),
          },
        ]}
      />
      <details open>
        <summary>按剩余应开全额与发票行逐项比对</summary>
        <ChecksTable checks={order.checks} caption="发票行与所选整张子采购单逐项比对" />
        <p className="matching-help">改小分配后，保存时由后端按实际填写重新比对。</p>
      </details>
      <label>
        审核说明（有不一致项或超出剩余应开时必填）
        <textarea
          rows={2}
          maxLength={300}
          value={note}
          disabled={busy}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <Button type="submit" variant="primary" disabled={busy || Boolean(order.block)}>
        {busy ? "保存中…" : replaceId ? "替换并通过整单关联" : "保存整单关联并通过"}
      </Button>
    </form>
  );
}
