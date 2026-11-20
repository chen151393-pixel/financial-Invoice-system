import { DataTable, type Column } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { AllocationRow } from "../types/declaration-detail";
import { DeclarationDetailLink } from "./DeclarationDetailLink";

const columns: Column<AllocationRow>[] = [
  {
    key: "number",
    header: "报关单",
    width: "26%",
    render: (row) => (
      <div className="settlement-cell">
        <strong>{row.current ? "本单" : <DeclarationDetailLink number={row.declarationNo} />}</strong>
        <span>
          {row.current && row.declarationNo} · {row.exportDate || "出口日期待补"}
        </span>
      </div>
    ),
  },
  { key: "amount", header: "报关金额", width: "18%", align: "right", render: (row) => money(row.amount) },
  {
    key: "receipts",
    header: "冲抵的银行收汇（推算）",
    width: "40%",
    render: (row) =>
      row.receipts.length ? (
        <div className="settlement-cell">
          {row.receipts.map((receipt) => (
            <div key={receipt.receiptId}>
              <span>
                {receipt.date} · {receipt.reference || `流水 #${receipt.receiptId}`}
              </span>
              <br />
              <strong>本单冲抵 {money(receipt.appliedAmount)}</strong> · 流水金额{" "}
              {money(receipt.receiptAmount)}
              {receipt.thirdParty && (
                <small className="settlement-declaration__payer">三方代付 · 付款人 {receipt.payer}</small>
              )}
            </div>
          ))}
        </div>
      ) : (
        "尚无可冲抵收汇"
      ),
  },
  {
    key: "outstanding",
    header: "未收",
    width: "16%",
    align: "right",
    render: (row) => <strong>{money(row.outstandingAmount)}</strong>,
  },
];
export function DeclarationAllocationTable({ rows }: { rows: AllocationRow[] }) {
  return (
    <DataTable
      label="银行收汇冲抵推算明细"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.declarationNo}
      density="compact"
      minWidth={580}
      rowTone={(row) => (row.current ? "accent" : undefined)}
      maxHeight={360}
    />
  );
}
