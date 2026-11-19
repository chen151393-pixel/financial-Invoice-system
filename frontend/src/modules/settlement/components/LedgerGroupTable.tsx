import { Link } from "react-router";
import { settlementDirectDocumentsPath } from "../../../app/paths";
import { useId, useState } from "react";
import { Badge, Button, DataTable, Icon, type Column, type Tone } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { LedgerEntry, LedgerGroup, LedgerStatus } from "../types";

type Row = LedgerEntry & { index: number };
type SummaryRow = { group: LedgerGroup; id: string };

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
    width: "9%",
    render: (row) => <Badge tone={row.kind === "export" ? "neutral" : "success"}>{row.kindLabel}</Badge>,
  },
  { key: "exportCompany", header: "出口抬头", width: "12%", render: (row) => row.exportCompany },
  { key: "exportDate", header: "出口日期", align: "center", width: "10%", render: (row) => row.exportDate },
  {
    key: "exportAmount",
    header: "出口金额",
    align: "right",
    width: "10%",
    render: (row) => amount(row.exportAmount),
  },
  { key: "receiptCompany", header: "收汇抬头", width: "12%", render: (row) => row.receiptCompany },
  {
    key: "receiptDate",
    header: "实际到账日期",
    align: "center",
    width: "10%",
    render: (row) => row.receiptDate,
  },
  {
    key: "receiptAmount",
    header: "收汇金额",
    align: "right",
    width: "10%",
    render: (row) => amount(row.receiptAmount),
  },
  {
    key: "source",
    header: "真实报关单号 / 银行流水号",
    width: "17%",
    render: (row) => (
      <div className="settlement-cell">
        {row.sourceNo || "—"}
        {row.thirdParty && <span>三方代付 · 付款人 {row.payerName}</span>}
      </div>
    ),
  },
  {
    key: "balance",
    header: "余额",
    align: "right",
    width: "10%",
    render: (row) => <strong>{money(row.balance)}</strong>,
  },
];

/** 展示总账汇总下的原始流水与截至每笔的余额。 */
export function LedgerGroupTable({ group }: { group: LedgerGroup }) {
  return (
    <DataTable
      label={`${group.consignee} ${group.currency} 流水`}
      columns={[
        ...COLUMNS,
        {
          key: "documents",
          header: "资料",
          render: (row) =>
            row.kind === "export" ? (
              <Link to={settlementDirectDocumentsPath(group.consignee, row.sourceNo)}>办理资料</Link>
            ) : (
              "—"
            ),
        },
      ]}
      rows={group.entries.map((entry, index) => ({ ...entry, index }))}
      rowKey={(row) => String(row.index)}
      minWidth={1080}
      density="compact"
    />
  );
}

export function LedgerSummaryTable({ groups }: { groups: LedgerGroup[] }) {
  const [expanded, setExpanded] = useState<string[]>([]);
  const tableId = useId();
  const rows = groups.map((group, index) => ({ group, id: `${tableId}-${index}` }));
  const columns: Column<SummaryRow>[] = [
    {
      key: "consignee",
      header: "境外收货人",
      width: "24%",
      render: ({ group, id }) => {
        const open = expanded.includes(id);
        return (
          <>
            <Button
              className="settlement-ledger__toggle"
              variant="ghost"
              size="sm"
              aria-expanded={open}
              aria-controls={open ? id : undefined}
              aria-label={`${open ? "收起" : "展开"} ${group.consignee} ${group.currency} 的流水`}
              onClick={() =>
                setExpanded((current) =>
                  current.includes(id) ? current.filter((row) => row !== id) : [...current, id],
                )
              }
            >
              <Icon name="chevronRight" />
              <strong>{group.consignee}</strong>
            </Button>
            {group.currency !== "USD" && <div className="settlement-ledger__meta">{group.currency}</div>}
          </>
        );
      },
    },
    {
      key: "receivingCompany",
      header: "收款人（收汇抬头）",
      width: "18%",
      render: ({ group }) => group.receivingCompany || "—",
    },
    {
      key: "status",
      header: "状态",
      width: "80px",
      render: ({ group }) => <Badge tone={STATUS_TONES[group.status]}>{group.statusLabel}</Badge>,
    },
    {
      key: "documents",
      header: "资料",
      render: ({ group }) => <Link to={settlementDirectDocumentsPath(group.consignee)}>报关资料</Link>,
    },
    {
      key: "opening",
      header: "期初差额",
      align: "right",
      render: ({ group }) => money(group.openingBalance),
    },
    { key: "export", header: "本期出口", align: "right", render: ({ group }) => money(group.exportTotal) },
    { key: "receipt", header: "本期收汇", align: "right", render: ({ group }) => money(group.receiptTotal) },
    {
      key: "balance",
      header: "期末差额",
      align: "right",
      render: ({ group }) => <strong>{money(group.balance)}</strong>,
    },
  ];
  return (
    <DataTable
      label="直接收汇汇总"
      columns={columns}
      rows={rows}
      rowKey={({ id }) => id}
      minWidth={800}
      density="compact"
      renderDetails={({ group, id }) =>
        expanded.includes(id) ? (
          <div id={id} className="settlement-ledger__detail">
            {group.entries.length ? <LedgerGroupTable group={group} /> : <p>本期无流水</p>}
          </div>
        ) : null
      }
    />
  );
}
