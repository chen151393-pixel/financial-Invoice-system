import { Badge, DataTable, type Column, type Tone } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { LedgerEntry, LedgerGroup, LedgerStatus } from "../types";

type Row = LedgerEntry & { index: number };

const STATUS_TONES: Record<LedgerStatus, Tone> = {
  outstanding: "progress",
  settled: "success",
  overpaid: "info",
};

// 另一侧为空的金额留空，不显示占位符
const amount = (value: string) => (value ? money(value) : "");

const COLUMNS: Column<Row>[] = [
  {
    key: "kind",
    header: "事务类型",
    width: "92px",
    render: (row) => <Badge tone={row.kind === "export" ? "neutral" : "success"}>{row.kindLabel}</Badge>,
  },
  { key: "exportCompany", header: "出口抬头", width: "104px", render: (row) => row.exportCompany },
  { key: "exportDate", header: "出口日期", width: "104px", render: (row) => row.exportDate },
  {
    key: "exportAmount",
    header: "出口金额",
    align: "right",
    width: "124px",
    render: (row) => amount(row.exportAmount),
  },
  { key: "receiptCompany", header: "收汇抬头", width: "104px", render: (row) => row.receiptCompany },
  { key: "receiptDate", header: "收汇日期", width: "104px", render: (row) => row.receiptDate },
  {
    key: "receiptAmount",
    header: "收汇金额",
    align: "right",
    width: "124px",
    render: (row) => amount(row.receiptAmount),
  },
  {
    key: "balance",
    header: "期末余额",
    align: "right",
    width: "124px",
    render: (row) => <strong>{money(row.balance)}</strong>,
  },
  {
    key: "source",
    header: "来源单据",
    render: (row) => (
      <div className="settlement-cell">
        {`${row.kind === "export" ? "报关单" : "银行收汇"} ${row.sourceNo || "—"}`}
        {row.thirdParty && <span>三方代付 · 付款人 {row.payerName}</span>}
      </div>
    ),
  },
];

/** 一家境外收货人（一个币种）的流水：出口加、收汇减，期末余额由后端逐笔累计。 */
export function LedgerGroupTable({ group }: { group: LedgerGroup }) {
  return (
    <section className="settlement-ledger" aria-label={`${group.consignee} ${group.currency} 收汇明细`}>
      <div className="settlement-ledger__head">
        <div className="settlement-badges">
          <strong>{group.consignee}</strong>
          <Badge tone={STATUS_TONES[group.status]}>{group.statusLabel}</Badge>
        </div>
        <span>
          {group.currency} · 出口 {money(group.exportTotal)} · 收汇 {money(group.receiptTotal)} · 期末余额{" "}
          <strong>{money(group.balance)}</strong>
        </span>
      </div>
      <DataTable
        label={`${group.consignee} ${group.currency} 流水`}
        columns={COLUMNS}
        rows={group.entries.map((entry, index) => ({ ...entry, index }))}
        rowKey={(row) => String(row.index)}
        minWidth={1040}
        density="compact"
      />
    </section>
  );
}
