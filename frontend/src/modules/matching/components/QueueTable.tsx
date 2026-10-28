import { Link } from "react-router";
import { matchingInvoicePath } from "../../../app/paths";
import { Badge, DataTable } from "../../../shared/components/ui";
import { tierLabels, type InvoiceQueueRow } from "../types/matching";

export const batchable = (row: InvoiceQueueRow) => row.batch.allowed;

export function QueueTable({
  rows,
  selected,
  onToggle,
  onToggleAll,
  busy = false,
}: {
  rows: InvoiceQueueRow[];
  selected: string[];
  onToggle: (id: string, checked: boolean) => void;
  onToggleAll: (checked: boolean) => void;
  busy?: boolean;
}) {
  const candidates = rows.filter(batchable);
  return (
    <DataTable
      label="待审核发票"
      rows={rows}
      rowKey={(row) => row.invoice.id}
      minWidth={1100}
      columns={[
        {
          key: "select",
          width: "44px",
          header: (
            <input
              type="checkbox"
              aria-label="选择本页全部可批量通过的发票"
              disabled={busy || candidates.length === 0}
              checked={candidates.length > 0 && candidates.every((row) => selected.includes(row.invoice.id))}
              onChange={(event) => onToggleAll(event.target.checked)}
            />
          ),
          render: (row) => (
            <input
              type="checkbox"
              aria-label={`选择发票 ${row.invoice.number}`}
              disabled={busy || !row.batch.allowed}
              checked={selected.includes(row.invoice.id)}
              onChange={(event) => onToggle(row.invoice.id, event.target.checked)}
            />
          ),
        },
        {
          key: "invoice",
          width: "220px",
          header: "发票号码 / 销售方",
          render: ({ invoice }) => (
            <div className="matching-cell">
              <strong className="matching-nowrap">{invoice.number}</strong>
              <small>{invoice.seller || "—"}</small>
            </div>
          ),
        },
        { key: "date", header: "开票日期", width: "105px", render: ({ invoice }) => invoice.date || "—" },
        {
          key: "gross",
          header: "票面价税合计",
          align: "right",
          render: ({ invoice }) => (
            <span className="matching-nowrap">
              {invoice.gross ?? "—"} {invoice.currency}
            </span>
          ),
        },
        {
          key: "proposals",
          header: "待审核明细",
          align: "right",
          render: (row) => `${row.proposalCount} 条`,
        },
        {
          key: "purchase",
          header: "建议子采购单",
          render: (row) => (
            <div className="matching-cell">
              {row.purchaseOrders.map((order) => (
                <span key={order}>{order || "—"}</span>
              ))}
            </div>
          ),
        },
        {
          key: "confidence",
          header: "置信度（最低）",
          render: (row) => (
            <Badge tone={row.tier === "low" ? "warning" : "info"}>
              {row.confidence}% · {tierLabels[row.tier]}
            </Badge>
          ),
        },
        {
          key: "conditions",
          header: "审核条件",
          render: (row) => (
            <div className="matching-cell">
              {row.anomalies.length > 0 && (
                <span className="matching-anomalies" aria-label={`异常：${row.anomalies.join("、")}`}>
                  {row.anomalies.map((name) => (
                    <Badge key={name} tone="warning">
                      {name}
                    </Badge>
                  ))}
                </span>
              )}
              <small>{row.batch.reason}</small>
            </div>
          ),
        },
        {
          key: "action",
          header: "操作",
          width: "88px",
          render: (row) => (
            <Link className="matching-review-link" to={matchingInvoicePath(row.invoice.id)}>
              审核详情
            </Link>
          ),
        },
      ]}
    />
  );
}
