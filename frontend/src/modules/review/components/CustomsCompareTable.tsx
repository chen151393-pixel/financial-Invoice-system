import { Badge, DataTable, type Column } from "../../../shared/components/ui";
import type { CustomsCompareGroup, CustomsItem, CustomsNsLine } from "../customs-types";

type CompareRow =
  | { kind: "ns"; key: string; group: CustomsCompareGroup; line: CustomsNsLine; first: boolean }
  | { kind: "customs"; key: string; group: CustomsCompareGroup; item: CustomsItem; first: boolean };

const dash = (value: string) => value || "—";

/**
 * 一张报关单的明细比对：同一比对组内 NS 报关行（白底）在前、海关项（浅蓝底）在后，
 * 比对结果写在组内第一行。分组、结论与说明均来自后端，前端不合计数量、不判断一致。
 */
export function CustomsCompareTable({
  declarationNo,
  groups,
}: {
  declarationNo: string;
  groups: CustomsCompareGroup[];
}) {
  const rows: CompareRow[] = groups.flatMap((group, index) => {
    const nsRows = group.nsLines.map((line) => ({
      kind: "ns" as const,
      key: `${index}-ns-${line.id}`,
      group,
      line,
    }));
    const itemRows = group.items.map((item) => ({
      kind: "customs" as const,
      key: `${index}-item-${item.itemNo}`,
      group,
      item,
    }));
    return [...nsRows, ...itemRows].map((row, position) => ({ ...row, first: position === 0 }));
  });
  const columns: Column<CompareRow>[] = [
    {
      key: "source",
      header: "来源",
      width: "56px",
      render: (row) => (
        <span className="cm-source" data-source={row.kind}>
          {row.kind === "ns" ? "NS" : "海关"}
        </span>
      ),
    },
    {
      key: "no",
      header: "行 / 项号",
      width: "72px",
      render: (row) => (row.kind === "ns" ? `行 ${dash(row.line.lineNo)}` : `项 ${row.item.itemNo}`),
    },
    {
      key: "code",
      header: "商品代码",
      width: "104px",
      render: (row) => dash(row.kind === "ns" ? row.line.itemCode : row.item.hsCode),
    },
    {
      key: "name",
      header: "品名",
      render: (row) => (row.kind === "ns" ? <strong>{dash(row.line.name)}</strong> : dash(row.item.name)),
    },
    {
      key: "spec",
      header: "规格型号",
      render: (row) => dash(row.kind === "ns" ? row.line.specification : row.item.specification),
    },
    {
      key: "quantity",
      header: "数量",
      align: "right",
      width: "120px",
      render: (row) => dash(row.kind === "ns" ? row.line.quantity : row.item.quantity),
    },
    {
      key: "unit",
      header: "单位",
      width: "64px",
      render: (row) => dash(row.kind === "ns" ? row.line.unit : row.item.unit),
    },
    {
      key: "legal",
      header: "法定数量",
      align: "right",
      width: "140px",
      render: (row) =>
        row.kind === "customs" && row.item.legalQuantity
          ? `${row.item.legalQuantity} ${row.item.legalUnit}`
          : "—",
    },
    {
      key: "total",
      header: "成交总价",
      align: "right",
      width: "120px",
      render: (row) =>
        row.kind === "customs" && row.item.total ? `${row.item.currency} ${row.item.total}`.trim() : "—",
    },
    {
      key: "result",
      header: "比对结果",
      width: "24%",
      render: (row) =>
        row.first ? (
          <span className="cm-result">
            <Badge tone={row.group.consistent ? "success" : "warning"}>{row.group.label}</Badge>
            <span>{row.group.note}</span>
          </span>
        ) : (
          <span className="cm-muted">同组</span>
        ),
    },
  ];
  return (
    <DataTable
      label={`报关单 ${declarationNo} 明细比对`}
      columns={columns}
      rows={rows}
      rowKey={(row) => row.key}
      density="compact"
      rowTone={(row) => (row.kind === "customs" ? "accent" : undefined)}
      minWidth={1040}
    />
  );
}
