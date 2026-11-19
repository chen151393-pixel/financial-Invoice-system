import { Link } from "react-router";
import { settlementBatchListPath, settlementLedgerPath } from "../../../app/paths";
import { Badge, DataTable, type Column } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { OverviewCustomer } from "../types/overview";

const COLUMNS: Column<OverviewCustomer>[] = [
  {
    key: "consignee",
    header: "境外收货人",
    width: "28%",
    render: (row) => (
      <div className="settlement-cell">
        <strong>{row.consignee}</strong>
        <span>{row.declarationCount} 张报关单</span>
      </div>
    ),
  },
  {
    key: "route",
    header: "回款路径",
    render: (row) => <Badge tone={row.route === "hk_transit" ? "info" : "neutral"}>{row.routeLabel}</Badge>,
  },
  { key: "currency", header: "币种", render: (row) => row.currency },
  { key: "declared", header: "报关应收汇", align: "right", render: (row) => money(row.declaredTotal) },
  { key: "received", header: "实收汇金额", align: "right", render: (row) => money(row.receivedTotal) },
  {
    key: "outstanding",
    header: "未收汇金额",
    align: "right",
    render: (row) => <strong>{money(row.outstanding)}</strong>,
  },
  { key: "fee", header: "已登记手续费", align: "right", render: (row) => money(row.receivedFee) },
  {
    key: "details",
    header: "查看",
    render: (row) => (
      <Link
        to={
          row.route === "hk_transit"
            ? settlementBatchListPath(row.consignee)
            : settlementLedgerPath(row.consignee)
        }
      >
        {row.route === "hk_transit" ? "香港中转批次" : "直接收汇明细"}
      </Link>
    ),
  },
];

export function OverviewCustomers({ rows }: { rows: OverviewCustomer[] }) {
  return (
    <DataTable
      label="客户收汇明细"
      rows={rows}
      columns={COLUMNS}
      rowKey={(row) => `${row.route}-${row.currency}-${row.consignee}`}
      minWidth={1000}
    />
  );
}
