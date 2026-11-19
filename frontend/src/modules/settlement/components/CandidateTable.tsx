import { Link } from "react-router";
import { paths, settlementReceiptPath } from "../../../app/paths";
import { Badge, DataTable, type Column } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { Candidate } from "../types";

/** 应收页只读；香港待登记页传入 selection 后才显示勾选。 */
export function CandidateTable({
  rows,
  selection,
}: {
  rows: Candidate[];
  selection?: { selected: string[]; onToggle: (row: Candidate) => void };
}) {
  const columns: Column<Candidate>[] = [
    ...(selection
      ? [
          {
            key: "pick",
            header: "选择",
            width: "56px",
            render: (row) =>
              row.handling === "batch" ? (
                <input
                  type="checkbox"
                  aria-label={`选择报关单 ${row.declarationNo}`}
                  checked={selection.selected.includes(row.declarationNo)}
                  disabled={Boolean(row.blockedReason)}
                  onChange={() => selection.onToggle(row)}
                />
              ) : (
                "—"
              ),
          } satisfies Column<Candidate>,
        ]
      : []),
    {
      key: "number",
      header: "报关单号 / CD",
      width: "150px",
      render: (row) => (
        <div className="settlement-cell">
          <strong>{row.declarationNo}</strong>
          <span>{row.recordNo || "—"}</span>
        </div>
      ),
    },
    {
      key: "orders",
      header: "销售订单",
      width: "120px",
      render: (row) => row.salesOrders.join("、") || "—",
    },
    { key: "consignee", header: "境外收货人", width: "260px", render: (row) => row.consignee || "—" },
    { key: "date", header: "出口日期", width: "110px", render: (row) => row.exportDate || "—" },
    {
      key: "route",
      header: "回款路径",
      width: "110px",
      render: (row) => (
        <span title={row.routeBasis}>
          <Badge tone={row.route === "hk_transit" ? "info" : "neutral"}>{row.routeLabel}</Badge>
        </span>
      ),
    },
    {
      key: "amount",
      header: "报关金额",
      align: "right",
      width: "150px",
      render: (row) => (row.amount ? `${row.currency} ${money(row.amount)}` : "—"),
    },
    {
      key: "state",
      header: "状态",
      width: "270px",
      render: (row) =>
        row.blockedReason ? (
          <Badge tone="warning">{row.blockedReason}</Badge>
        ) : row.handling === "ledger" ? (
          <Link to={paths.settlementDirect}>已进直接收汇明细</Link>
        ) : selection ? (
          <Badge tone="success">可登记回款</Badge>
        ) : (
          <Link to={settlementReceiptPath(row.consignee)}>去香港中转登记</Link>
        ),
    },
  ];

  return (
    <DataTable
      label="报关单明细"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.declarationNo}
      rowTone={(row) => (selection?.selected.includes(row.declarationNo) ? "accent" : undefined)}
      minWidth={1240}
    />
  );
}
