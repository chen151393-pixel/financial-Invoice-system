import { Alert, Button, DataTable, EmptyState, type Column } from "../../../shared/components/ui";
import type { ComparisonGroup, CustomsLine, PurchaseLine } from "../types";
import { UnitPriceMargin } from "./UnitPriceMargin";
import "./review-levels.css";

type ComparisonRow =
  | { kind: "customs"; line: CustomsLine; key: string }
  | { kind: "purchase"; line: PurchaseLine; key: string; customsLineNo?: number };

/** 报关行与它关联的采购行连续展示，共用列宽；不推断关联、不汇总金额。 */
export function CustomsRows({
  group,
  selectLine,
}: {
  group: ComparisonGroup;
  selectLine: (line: PurchaseLine) => void;
}) {
  const rows: ComparisonRow[] = group.customsLines.flatMap((line) => [
    { kind: "customs" as const, line, key: line.id },
    ...line.purchaseLines.map((purchase) => ({
      kind: "purchase" as const,
      line: purchase,
      key: `${line.id}-${purchase.id}`,
      customsLineNo: line.lineNo,
    })),
  ]);
  rows.push(
    ...group.unlinkedLines.map((line) => ({ kind: "purchase" as const, line, key: `unlinked-${line.id}` })),
  );

  // 不单设"来源"列：子采购行在首列向右缩进一级并以连线挂在所属报关行下，报关行加粗。
  const columns: Column<ComparisonRow>[] = [
    {
      key: "parent",
      header: "母采购单号",
      width: "15%",
      render: (row) =>
        row.kind === "customs" ? (
          <span className="fr-tree fr-tree--customs" aria-label={`报关第 ${row.line.lineNo} 行`}>
            <strong>{row.line.parent || "—"}</strong>
          </span>
        ) : (
          <span
            className="fr-tree fr-tree--purchase"
            aria-label={
              row.customsLineNo ? `报关第 ${row.customsLineNo} 行关联子采购` : "未关联报关行的子采购"
            }
          >
            {row.line.parent || "—"}
          </span>
        ),
    },
    {
      key: "child",
      header: "子采购单号",
      width: "14%",
      render: (row) =>
        row.kind === "purchase" ? (
          <>
            {row.line.child || "—"}
            {/* 订单口径的数量金额是整张子单，不是本次报关范围，须保留标注 */}
            {row.line.scope === "order" && <small>订单口径</small>}
            {Boolean(row.line.members?.length) && <small>合并 {row.line.members?.length} 行</small>}
          </>
        ) : (
          "—"
        ),
    },
    {
      key: "origin",
      header: "货源地",
      width: "6%",
      render: (row) => (row.kind === "customs" ? row.line.originPlace || "—" : "—"),
    },
    {
      key: "supplier",
      header: "供应商",
      width: "12%",
      render: (row) => (row.kind === "purchase" ? row.line.supplier || "未提供" : "—"),
    },
    { key: "name", header: "开票品名", width: "8%", render: ({ line }) => line.name || "未提供" },
    { key: "model", header: "规格型号", width: "10%", render: ({ line }) => line.model || "—" },
    {
      key: "quantity",
      header: "数量",
      width: "7%",
      align: "right",
      render: (row) => (
        <span
          aria-label={
            row.kind === "customs" ? "申报数量" : row.line.scope === "order" ? "子单数量" : "本次数量"
          }
        >
          {row.line.quantity || "未提供"}
        </span>
      ),
    },
    {
      key: "unit",
      header: "单位",
      width: "4%",
      align: "center",
      render: ({ line }) => line.unit || "未提供",
    },
    {
      key: "price",
      header: "单价",
      width: "6%",
      align: "right",
      render: (row) => (
        <span aria-label={row.kind === "customs" ? "申报单价" : "采购含税单价"}>
          {row.line.price || "未提供"}
        </span>
      ),
    },
    {
      key: "amount",
      header: "金额",
      width: "8%",
      align: "right",
      render: (row) => (
        <span
          aria-label={
            row.kind === "customs" ? "报关金额" : row.line.scope === "order" ? "订单金额" : "本次采购金额"
          }
        >
          <strong>{row.line.amount || "未提供"}</strong>
          <small>{row.line.currency || "未提供币种"}</small>
        </span>
      ),
    },
    {
      key: "action",
      header: "申报幅度（单价）/ 操作",
      width: "10%",
      align: "right",
      render: (row) => (
        <>
          {row.kind === "customs" && <UnitPriceMargin line={row.line} />}
          {row.kind === "purchase" && (
            <Button
              size="sm"
              aria-label={`查看明细：${row.line.name} ${row.line.child}`}
              onClick={() => selectLine(row.line)}
            >
              查看
            </Button>
          )}
        </>
      ),
    },
  ];

  return (
    <div className="fr-comparison-lines">
      {group.unlinkedLines.length > 0 && (
        <Alert tone="warning" title="有子采购行尚未关联报关行">
          未关联明细列在表格末尾，请核实来源关联。
        </Alert>
      )}
      {rows.length ? (
        <DataTable
          label={`${group.recordNumber} 报关与采购对照`}
          rows={rows}
          columns={columns}
          rowKey={(row) => row.key}
          rowTone={(row) => (row.kind === "purchase" ? "accent" : undefined)}
          density="compact"
          minWidth={1320}
        />
      ) : (
        <EmptyState title="暂无报关与采购明细" description="当前报关单尚未返回明细数据。" />
      )}
    </div>
  );
}
