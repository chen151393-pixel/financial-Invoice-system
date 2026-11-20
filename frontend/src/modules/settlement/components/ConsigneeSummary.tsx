import { Link } from "react-router";
import { settlementBatchListPath, settlementLedgerPath, settlementReceiptPath } from "../../../app/paths";
import { Badge, Button, DataTable, Progress, type Column } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { ReceivableCustomer } from "../types";
import { stageTone } from "./receivable-tones";

function dateRange(row: ReceivableCustomer) {
  if (!row.firstExportDate) return "—";
  return row.firstExportDate === row.lastExportDate
    ? row.firstExportDate
    : `${row.firstExportDate} 至 ${row.lastExportDate}`;
}

function columns(onDrill: (row: ReceivableCustomer) => void): Column<ReceivableCustomer>[] {
  return [
    {
      key: "consignee",
      header: "境外收货人 / 结汇阶段",
      width: "250px",
      render: (row) => (
        <div className="settlement-cell">
          <strong>{row.consignee || "—"}</strong>
          <div className="settlement-badges">
            {row.stages.map((stage) => (
              <Badge key={stage.stage} tone={stageTone(stage.stage)} dot={false}>
                {stage.label} {stage.count}
              </Badge>
            ))}
          </div>
          {row.oldestAgingDays !== null && <span>未结汇最久 {row.oldestAgingDays} 天</span>}
        </div>
      ),
    },
    {
      key: "route",
      header: "回款路径 / 出口抬头",
      width: "160px",
      render: (row) => (
        <div className="settlement-cell" title={row.routeBasis}>
          <div>
            <Badge tone={row.route === "hk_transit" ? "info" : "neutral"}>{row.routeLabel}</Badge>
          </div>
          <span>{row.exportCompanies.join("、") || "—"}</span>
        </div>
      ),
    },
    {
      key: "count",
      header: "报关单 / 出口日期",
      width: "150px",
      render: (row) => (
        <div className="settlement-cell">
          {row.count} 票<span>{dateRange(row)}</span>
          {row.issueCount > 0 && <span>{row.issueCount} 张金额缺失未计入</span>}
        </div>
      ),
    },
    {
      key: "money",
      header: "应收 / 已收 / 未收",
      width: "250px",
      render: (row) => (
        <div className="settlement-cell">
          <strong>{`${row.currency} ${money(row.amount)}`}</strong>
          <Progress
            width={row.receivedPercent}
            text={row.receivedPercentText}
            label={`${row.consignee} 已收比例`}
            tone={row.receivedPercent >= 100 ? "success" : "info"}
          />
          <span>
            {row.route === "hk_transit" ? "已登记到账" : "推算已收"} {money(row.receivedAmount)} · 未收{" "}
            {money(row.outstandingAmount)}
          </span>
          {row.overpaidAmount !== "0.00" && <span>客户超收 {money(row.overpaidAmount)}</span>}
        </div>
      ),
    },
    {
      key: "documents",
      header: "资料",
      width: "170px",
      render: (row) => (
        <div className="settlement-cell">
          <div>
            <Badge tone={row.documentIssueCount ? "warning" : "neutral"}>
              {row.documentIssueCount ? `${row.documentIssueCount} 票待处理` : "无待处理"}
            </Badge>
          </div>
          <span>{row.documentNote}</span>
        </div>
      ),
    },
    {
      key: "handling",
      header: "处理方式",
      width: "200px",
      render: (row) => (
        <div className="settlement-cell">
          {row.handling === "batch" ? (
            <>
              <Link
                to={
                  row.pendingCount
                    ? settlementReceiptPath(row.consignee)
                    : settlementBatchListPath(row.consignee)
                }
              >
                {row.pendingCount ? "去登记回款" : "香港中转批次"}
              </Link>
              <span>
                已建批次 {row.batchedCount} · 待登记 {row.pendingCount}
              </span>
              {row.alertCount > 0 && <span>{row.alertCount} 票香港滞留超期</span>}
            </>
          ) : (
            <>
              <Link to={settlementLedgerPath(row.consignee)}>客户总账</Link>
            </>
          )}
          <div>
            <Button size="sm" variant="ghost" onClick={() => onDrill(row)}>
              看 {row.count} 票明细
            </Button>
          </div>
        </div>
      ),
    },
  ];
}

/** 按境外收货人汇总的应收汇：已收、未收、阶段分布与资料情况均由后端给出。 */
export function ConsigneeSummary({
  rows,
  onDrill,
}: {
  rows: ReceivableCustomer[];
  onDrill: (row: ReceivableCustomer) => void;
}) {
  return (
    <DataTable
      label="按境外收货人汇总的应收汇"
      columns={columns(onDrill)}
      rows={rows}
      rowKey={(row) => `${row.consignee}|${row.currency}`}
      minWidth={1080}
    />
  );
}
