import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Badge, DataTable, type Column } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { ConsigneeTotal } from "../types";

const COLUMNS: Column<ConsigneeTotal>[] = [
  { key: "consignee", header: "境外收货人", render: (row) => <strong>{row.consignee || "—"}</strong> },
  {
    key: "route",
    header: "回款路径 / 判定依据",
    render: (row) => (
      <div className="settlement-cell">
        <div>
          <Badge tone={row.route === "hk_transit" ? "info" : "neutral"}>{row.routeLabel}</Badge>
        </div>
        <span>{row.routeBasis}</span>
      </div>
    ),
  },
  { key: "company", header: "出口抬头", render: (row) => row.exportCompanies.join("、") || "—" },
  {
    key: "count",
    header: "报关单数",
    align: "right",
    render: (row) => (
      <div className="settlement-cell">
        {row.count}
        {row.issueCount > 0 && <span>{row.issueCount} 张金额缺失未计入</span>}
      </div>
    ),
  },
  {
    key: "dates",
    header: "出口日期范围",
    width: "200px",
    render: (row) =>
      !row.firstExportDate
        ? "—"
        : row.firstExportDate === row.lastExportDate
          ? row.firstExportDate
          : `${row.firstExportDate} 至 ${row.lastExportDate}`,
  },
  {
    key: "amount",
    header: "应收汇金额",
    align: "right",
    render: (row) => <strong>{`${row.currency} ${money(row.amount)}`}</strong>,
  },
  {
    key: "handling",
    header: "处理方式",
    width: "230px",
    render: (row) =>
      row.handling === "batch" ? (
        <div className="settlement-cell">
          <Link to={paths.settlementHk}>香港中转批次</Link>
          <span>
            {row.batchedCount} 票已建批次 · {row.pendingCount} 票待登记回款
          </span>
        </div>
      ) : (
        <div className="settlement-cell">
          <Link to={paths.settlementDirect}>直接收汇明细</Link>
          <span>按收货人和收款人汇总差额</span>
        </div>
      ),
  },
];

/** 按境外收货人汇总的应收汇：路径判定、张数与金额均由后端给出。 */
export function ConsigneeSummary({ rows }: { rows: ConsigneeTotal[] }) {
  return (
    <DataTable
      label="按境外收货人汇总的应收汇"
      columns={COLUMNS}
      rows={rows}
      rowKey={(row) => `${row.consignee}|${row.currency}`}
      minWidth={980}
    />
  );
}
