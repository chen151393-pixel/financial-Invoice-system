import { Link } from "react-router";
import { matchingInvoicePath } from "../../../app/paths";
import { Badge, DataTable } from "../../../shared/components/ui";
import type { MatchPageInvoice, MatchingSummary } from "../types/matching";

/** 比对页“未生成建议 / 已审核通过”：发票与匹配状态均来自后端列表，前端只展示。 */
export function MatchStatusTable({
  rows,
  summaries,
}: {
  rows: MatchPageInvoice[];
  summaries: MatchingSummary[];
}) {
  const status = new Map(summaries.map((row) => [row.invoiceId, row]));
  return (
    <DataTable
      label="比对发票"
      rows={rows}
      rowKey={(row) => row.id}
      minWidth={760}
      columns={[
        {
          key: "number",
          header: "发票号码 / 销售方",
          render: (row) => (
            <div className="matching-cell">
              <strong>{row.number}</strong>
              <small>{row.seller || "—"}</small>
            </div>
          ),
        },
        { key: "date", header: "开票日期", width: "110px", render: (row) => row.date || "—" },
        {
          key: "gross",
          header: "票面价税合计",
          align: "right",
          render: (row) => (row.gross ? `${row.gross} ${row.currency}` : "—"),
        },
        {
          key: "status",
          header: "比对状态",
          render: (row) => {
            const summary = status.get(row.id);
            if (!summary) return "—";
            return (
              <Badge tone={summary.status === "confirmed" ? "success" : "neutral"}>{summary.label}</Badge>
            );
          },
        },
        {
          key: "action",
          header: "操作",
          width: "88px",
          render: (row) => (
            <Link className="matching-review-link" to={matchingInvoicePath(row.id)}>
              比对详情
            </Link>
          ),
        },
      ]}
    />
  );
}
