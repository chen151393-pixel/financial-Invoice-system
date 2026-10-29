import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  DataTable,
  ProgressRing,
} from "../../../shared/components/ui";
import { tierLabels, type InvoiceItem, type InvoiceMatching, type MatchingGroup } from "../types/matching";
import { ChecksTable } from "./ChecksTable";

type Mode = "confirm" | "reject" | null;

/** 发票行与一张或多张整张子采购单合计的比对；整组通过或驳回，比对结果与能力均来自后端。 */
export function GroupComparisonCard({
  group,
  item,
  invoice,
  busy,
  onConfirm,
  onReject,
}: {
  group: MatchingGroup;
  item: InvoiceItem;
  invoice: InvoiceMatching["invoice"];
  busy: boolean;
  onConfirm: (note: string) => Promise<boolean>;
  onReject: (note: string) => Promise<boolean>;
}) {
  const [mode, setMode] = useState<Mode>(null);
  const [note, setNote] = useState("");
  const part = group.items.find((row) => row.invoiceItemId === item.id);
  if (!part) return null;
  const orders = group.orders.map((order) => order.orderNo).join("、");
  const parents = [...new Set(group.orders.map((order) => order.parentOrderNo).filter(Boolean))].join("、");
  const units = [...new Set(part.lines.map((line) => line.unit).filter(Boolean))].join("、");
  const noteRequired = mode === "confirm" && group.noteReasons.length > 0;
  return (
    <Card className="matching-comparison" aria-label={`整单比对 ${orders}`}>
      <CardHeader
        title={`${group.orders[0]?.supplier || "子采购单"} · ${orders}`}
        description={
          <span className="matching-row">
            <Badge tone="info">待审核整单</Badge>
            <span>
              第 {item.lineNo || "—"} 行对应 {group.orders.length} 张整张子采购单，共 {part.lines.length}{" "}
              行明细
            </span>
          </span>
        }
        actions={
          <div className="matching-confidence">
            <ProgressRing value={part.confidence} text={`${part.confidence}%`} label="匹配置信度" />
            <span>
              <small>匹配置信度</small>
              <strong>{tierLabels[part.tier]}置信度</strong>
            </span>
          </div>
        }
      />
      <CardContent className="matching-comparison-content">
        <div className="matching-comparison-sides">
          <Card className="matching-source-side">
            <CardHeader title="进项发票行" description={invoice.number} />
            <CardContent>
              <p>{invoice.seller || "销售方未提供"}</p>
              <p className="matching-help">
                开票日期 {invoice.date || "—"} · 购买方 {invoice.buyer || "未提供"}
              </p>
              <strong>
                第 {item.lineNo || "—"} 行 · {item.item || "品名未提供"}
              </strong>
              <p>
                {item.quantity ?? "—"} {item.unit || ""} · 价税合计 {item.amount ?? "—"} {invoice.currency}
              </p>
              <p className="matching-help">
                金额 {item.net ?? "—"} · 税率 {item.taxRate ?? "—"} · 税额 {item.tax ?? "—"}
              </p>
            </CardContent>
          </Card>
          <Card className="matching-source-side matching-source-side--purchase">
            <CardHeader title="整张子采购单合计" description={orders} />
            <CardContent>
              <p>{group.orders[0]?.supplier || "—"}</p>
              <p className="matching-help">
                采购公司 {group.orders[0]?.company || "—"}
                {parents && ` · 母采购单 ${parents}`}
              </p>
              <strong>
                {group.orders.length} 张子采购单 · {part.lines.length} 行明细
              </strong>
              <p>
                {part.quantity} {units} · 含税合计 {part.amount}
              </p>
            </CardContent>
          </Card>
        </div>
        <ChecksTable checks={part.checks} caption="发票行与整张子采购单合计逐项比对" />
        <details className="matching-group-lines">
          <summary>查看子采购明细（{part.lines.length} 行）</summary>
          <DataTable
            label="整单所含子采购明细"
            rows={part.lines}
            rowKey={(row) => row.purchaseLineId}
            density="compact"
            minWidth={640}
            maxHeight={320}
            columns={[
              { key: "order", header: "子采购单", render: (row) => row.orderNo },
              {
                key: "item",
                header: "品名 / 规格",
                render: (row) => (
                  <span className="matching-cell">
                    {row.item || "—"}
                    {row.specification && <small>{row.specification}</small>}
                  </span>
                ),
              },
              {
                key: "quantity",
                header: "数量",
                align: "right",
                render: (row) => `${row.quantity} ${row.unit}`,
              },
              { key: "amount", header: "含税金额", align: "right", render: (row) => row.amount },
              { key: "rate", header: "税率", align: "right", render: (row) => row.taxRate ?? "未同步" },
            ]}
          />
        </details>
        {group.noteReasons.length > 0 && (
          <ul className="matching-reasons" aria-label="通过时需填写说明的原因">
            {group.noteReasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        )}
        <p className="matching-help">{group.confirm.reason}</p>
        {mode === null ? (
          <div className="matching-row matching-review-actions">
            <Button
              variant="primary"
              disabled={busy || !group.confirm.allowed}
              onClick={() => setMode("confirm")}
            >
              确认整单通过
            </Button>
            <Button disabled={busy || !group.reject.allowed} onClick={() => setMode("reject")}>
              驳回整单
            </Button>
          </div>
        ) : (
          <form
            className="matching-form"
            onSubmit={(event) => {
              event.preventDefault();
              void (mode === "confirm" ? onConfirm(note) : onReject(note)).then((saved) => {
                if (saved) setMode(null);
              });
            }}
          >
            <label>
              {noteRequired ? "审核说明（必填）" : "说明（选填）"}
              <textarea
                rows={2}
                maxLength={300}
                value={note}
                disabled={busy}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            <div className="matching-row">
              <Button type="submit" variant="primary" disabled={busy}>
                {busy
                  ? "提交中…"
                  : mode === "confirm"
                    ? `确认通过 ${group.orders.length} 张整单`
                    : "确认驳回整单"}
              </Button>
              <Button disabled={busy} onClick={() => setMode(null)}>
                返回
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
