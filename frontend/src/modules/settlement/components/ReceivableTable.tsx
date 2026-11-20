import { Link } from "react-router";
import {
  settlementBatchListPath,
  settlementDirectDocumentsPath,
  settlementLedgerPath,
  settlementReceiptPath,
} from "../../../app/paths";
import { Badge, DataTable, Progress, type Column } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { ReceivableItem } from "../types";
import { documentTone, stageTone } from "./receivable-tones";

/** 下一步去哪里办：香港中转到登记回款或所在批次，直接收汇到客户总账；资料在批次或资料页办理。 */
function NextStep({ row }: { row: ReceivableItem }) {
  if (row.stage === "issue")
    return (
      <div className="settlement-cell">
        <span>先处理海关回执数据</span>
      </div>
    );
  if (row.route === "hk_transit") {
    if (!row.batchNo) return <Link to={settlementReceiptPath(row.consignee)}>去登记回款</Link>;
    const text = { collected: "去批次办资料", remit: "去批次登记汇回" }[row.stage as string] ?? "查看批次";
    return (
      <div className="settlement-cell">
        <Link to={settlementBatchListPath("", row.batchNo)}>{text}</Link>
        <span>{row.batchNo}</span>
      </div>
    );
  }
  return (
    <div className="settlement-cell">
      <Link to={settlementLedgerPath(row.consignee)}>客户总账</Link>
      <Link to={settlementDirectDocumentsPath(row.consignee, row.declarationNo)}>留存资料</Link>
    </div>
  );
}

const COLUMNS: Column<ReceivableItem>[] = [
  {
    key: "number",
    header: "报关单号 / CD",
    width: "190px",
    render: (row) => (
      <div className="settlement-cell">
        <strong>{row.declarationNo}</strong>
        <span>{row.recordNo || "—"}</span>
      </div>
    ),
  },
  {
    key: "consignee",
    header: "境外收货人 / 回款路径",
    width: "240px",
    render: (row) => (
      <div className="settlement-cell">
        {row.consignee || "—"}
        <div className="settlement-badges" title={row.routeBasis}>
          <Badge tone={row.route === "hk_transit" ? "info" : "neutral"}>{row.routeLabel}</Badge>
          <span>{row.exportCompany || "—"}</span>
        </div>
      </div>
    ),
  },
  {
    key: "date",
    header: "出口日期 / 账龄",
    width: "110px",
    render: (row) => (
      <div className="settlement-cell">
        {row.exportDate || "—"}
        <span>{row.agingDays === null ? "—" : `${row.agingDays} 天`}</span>
      </div>
    ),
  },
  {
    key: "money",
    header: "报关金额 / 收款",
    width: "250px",
    render: (row) => (
      <div className="settlement-cell" title={row.receivedBasis}>
        <strong>{row.amount ? `${row.currency} ${money(row.amount)}` : "—"}</strong>
        {row.stage !== "issue" && (
          <>
            <Progress
              width={row.receivedPercent}
              text={row.receivedPercentText}
              label={`报关单 ${row.declarationNo} 已收比例`}
              tone={row.receivedPercent >= 100 ? "success" : "info"}
            />
            <span>
              {row.route === "direct" ? "推算已收" : "已收"} {money(row.receivedAmount)} · 未收{" "}
              {money(row.outstandingAmount)}
            </span>
          </>
        )}
      </div>
    ),
  },
  {
    key: "documents",
    header: "资料",
    width: "190px",
    render: (row) => (
      <div className="settlement-cell">
        <div>
          <Badge tone={documentTone(row.documentStatus)}>{row.documentLabel}</Badge>
        </div>
        {row.documentNote && <span>{row.documentNote}</span>}
      </div>
    ),
  },
  {
    key: "stage",
    header: "结汇状态 / 下一步",
    width: "170px",
    render: (row) => (
      <div className="settlement-cell">
        <div className="settlement-badges">
          <Badge tone={stageTone(row.stage)}>{row.stageLabel}</Badge>
          {row.alert && <Badge tone="danger">{row.alert}</Badge>}
        </div>
        {row.issue && <span>{row.issue}</span>}
        <NextStep row={row} />
      </div>
    ),
  },
];

/** 报关单明细：一张报关单一行，收款、资料、结汇状态与下一步全部来自后端。 */
export function ReceivableTable({ rows }: { rows: ReceivableItem[] }) {
  return (
    <DataTable
      label="报关单明细"
      columns={COLUMNS}
      rows={rows}
      rowKey={(row) => row.declarationNo}
      minWidth={1150}
    />
  );
}
