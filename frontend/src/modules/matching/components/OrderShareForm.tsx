import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  ProgressRing,
} from "../../../shared/components/ui";
import { tierLabels, type InvoiceItem, type InvoiceMatching } from "../types/matching";
import type { ManualOrderBody, ManualOrderCandidate } from "../types/manual-order";
import { ChecksTable } from "./ChecksTable";
import { InvoiceLineSide } from "./InvoiceLineSide";

type Shares = Record<string, { quantity: string; amount: string }>;

/** 候选来源：best＝打开时默认展示的置信度最高候选，picked＝用户按单号查询后改选。 */
export type OrderOrigin = "best" | "picked";

/**
 * 选中整张子采购单后的整单比对与本票分配，布局与自动建议的整单比对卡一致。
 * 明细默认取后端给出的剩余应开，可改小以支持部分开票；合计、比对与校验均由后端完成。
 */
export function OrderShareForm({
  order,
  origin,
  item,
  invoice,
  invoiceId,
  invoiceVersionId,
  replaceId,
  reason,
  busy,
  onCreate,
}: {
  order: ManualOrderCandidate;
  origin: OrderOrigin;
  item: InvoiceItem;
  invoice: InvoiceMatching["invoice"];
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
    <Card className="matching-comparison" aria-label={`整单比对 ${order.orderNo}`}>
      <CardHeader
        title={`${order.supplier || "子采购单"} · ${order.orderNo}`}
        description={
          <span className="matching-row">
            {origin === "best" ? (
              <Badge tone="info">置信度最高 · 未保存</Badge>
            ) : (
              <Badge tone="progress">手动选择 · 未保存</Badge>
            )}
            <span>
              第 {item.lineNo || "—"} 行对应 1 张整张子采购单，共 {order.lines.length} 行明细
            </span>
          </span>
        }
        actions={
          <div className="matching-confidence">
            <ProgressRing value={order.confidence} text={`${order.confidence}%`} label="匹配置信度" />
            <span>
              <small>匹配置信度</small>
              <strong>{tierLabels[order.tier]}置信度</strong>
            </span>
          </div>
        }
      />
      <CardContent className="matching-comparison-content">
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
          <div className="matching-comparison-sides">
            <InvoiceLineSide invoice={invoice} item={item} />
            <Card className="matching-source-side matching-source-side--purchase">
              <CardHeader title="整张子采购单合计" description={order.orderNo} />
              <CardContent>
                <p>{order.supplier || "—"}</p>
                <p className="matching-help">
                  采购公司 {order.company || "—"}
                  {order.parentOrderNo && ` · 母采购单 ${order.parentOrderNo}`}
                </p>
                <strong>1 张子采购单 · {order.lines.length} 行明细</strong>
                <p>
                  剩余应开 {order.remainingQuantity ?? "—"} {order.unit} · 含税合计{" "}
                  {order.remainingAmount ?? "—"} {order.currency}
                </p>
                {order.recordNumbers.length > 0 && (
                  <p className="matching-help">报关 {order.recordNumbers.join("、")}</p>
                )}
              </CardContent>
            </Card>
          </div>
          {order.block && (
            <Alert tone="danger" title="该子采购单不能关联">
              {order.block}
            </Alert>
          )}
          <ChecksTable checks={order.checks} caption="发票行与整张子采购单逐项比对（按剩余应开全额）" />
          <div className="matching-share-heading">
            <strong>本票分配</strong>
            <span className="matching-help">
              默认填入剩余应开；部分开票时改小，本票不开的明细数量和金额填 0。保存时由后端按实际填写重新比对。
            </span>
          </div>
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
          <div className="matching-row matching-review-actions">
            <Button type="submit" variant="primary" disabled={busy || Boolean(order.block)}>
              {busy ? "保存中…" : replaceId ? "替换并通过整单关联" : "保存整单关联并通过"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
