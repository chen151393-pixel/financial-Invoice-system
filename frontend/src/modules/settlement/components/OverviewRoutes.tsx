import { Link } from "react-router";
import { settlementBatchListPath, settlementLedgerPath } from "../../../app/paths";
import { Card, CardContent, CardHeader, DataTable, type Column } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { OverviewRoute, OverviewTotal } from "../types/overview";

interface RouteRow extends OverviewRoute {
  currency: string;
}

const COLUMNS: Column<RouteRow>[] = [
  { key: "route", header: "收汇路径", render: (row) => <strong>{row.routeLabel}</strong> },
  { key: "currency", header: "币种", render: (row) => row.currency },
  { key: "declared", header: "报关应收汇", align: "right", render: (row) => money(row.declaredTotal) },
  { key: "received", header: "实收汇金额", align: "right", render: (row) => money(row.receivedTotal) },
  {
    key: "outstanding",
    header: "未收汇金额",
    align: "right",
    render: (row) => <strong>{money(row.outstanding)}</strong>,
  },
];

/** 使用后端全量路径汇总，不对当前页客户记录加总，不混合不同币种。 */
export function OverviewRoutes({ totals, consignee }: { totals: OverviewTotal[]; consignee: string }) {
  const rows = totals.flatMap((total) =>
    total.routes.map((route) => ({ ...route, currency: total.currency })),
  );
  const columns: Column<RouteRow>[] = [
    ...COLUMNS,
    {
      key: "details",
      header: "查看明细",
      render: (row) => (
        <Link
          to={
            row.route === "hk_transit" ? settlementBatchListPath(consignee) : settlementLedgerPath(consignee)
          }
        >
          {row.route === "hk_transit" ? "查看香港中转批次" : "查看直接收汇明细"}
        </Link>
      ),
    },
  ];
  return (
    <Card>
      <CardHeader
        title="按收汇路径查看"
        description="同一笔客户收款只统计一次；香港汇回境内不再次增加实收汇金额。"
      />
      <CardContent flush>
        <DataTable
          label="收汇路径汇总"
          rows={rows}
          columns={columns}
          rowKey={(row) => `${row.currency}-${row.route}`}
          minWidth={760}
        />
      </CardContent>
    </Card>
  );
}
