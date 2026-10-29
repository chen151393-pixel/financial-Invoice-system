import { Alert, Badge, Button, DataTable, EmptyState, type Column } from "../../../shared/components/ui";
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

  // 不单设"来源"列：报关行与子采购行的单号同一缩进对齐，子采购行以连线挂在所属报关行下，报关行加粗。
  const columns: Column<ComparisonRow>[] = [
    {
      key: "parent",
      header: "母采购单号",
      width: "17%",
      render: (row) =>
        row.kind === "customs" ? (
          <span
            className="fr-tree fr-tree--customs"
            title={row.line.parent || undefined}
            aria-label={`报关第 ${row.line.lineNo} 行`}
          >
            <strong>{row.line.parent || "—"}</strong>
          </span>
        ) : (
          <span
            className="fr-tree fr-tree--purchase"
            title={row.line.parent || undefined}
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
      width: "17%",
      render: (row) =>
        row.kind === "purchase" ? (
          <span className="fr-order-no">
            {row.line.child || "—"}
            {/* 数量和单价口径由后端明确返回。 */}
            <small className="fr-order-tag">{row.line.scope === "order" ? "订单口径" : "报关数量"}</small>
            {Boolean(row.line.members?.length) && (
              <small className="fr-order-tag">合并 {row.line.members?.length} 行</small>
            )}
          </span>
        ) : (
          "—"
        ),
    },
    {
      key: "origin",
      header: "货源地",
      width: "5%",
      render: (row) => (row.kind === "customs" ? row.line.originPlace || "—" : "—"),
    },
    {
      key: "supplier",
      header: "供应商",
      width: "11%",
      render: (row) => (row.kind === "purchase" ? row.line.supplier || "未提供" : "—"),
    },
    { key: "name", header: "开票品名", width: "7%", render: ({ line }) => line.name || "未提供" },
    { key: "model", header: "规格型号", width: "6%", render: ({ line }) => line.model || "—" },
    {
      key: "quantity",
      header: "数量",
      width: "7%",
      align: "right",
      render: (row) => (
        <span
          aria-label={
            row.kind === "customs" ? "申报数量" : row.line.scope === "order" ? "子单数量" : "子采购报关数量"
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
      render: (row) =>
        row.kind === "customs" && row.line.priceEstimated ? (
          // NS 未填申报单价时，后端按报关金额 ÷ 报关数量试算；前端只标注，不重算。
          <span
            className="fr-price-estimated"
            aria-label={`申报单价 ${row.line.price}，NS 未填写，按报关金额除以报关数量试算`}
            title="NS 未填写申报单价，按报关金额 ÷ 报关数量试算"
          >
            {row.line.price}
            <Badge tone="info" dot={false}>
              试算
            </Badge>
          </span>
        ) : (
          <span aria-label={row.kind === "customs" ? "申报单价" : "采购含税单价"}>
            {row.line.price || "未提供"}
            {row.kind === "purchase" && row.line.scope === "declared" && (
              <small> / {row.line.purchaseUnit || "采购单位未提供"}</small>
            )}
          </span>
        ),
    },
    {
      key: "amount",
      header: "金额",
      width: "9%",
      align: "right",
      render: (row) => (
        <span
          aria-label={
            row.kind === "customs" ? "报关金额" : row.line.scope === "order" ? "订单金额" : "采购含税金额"
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
      width: "11%",
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
          minWidth={1400}
        />
      ) : (
        <EmptyState title="暂无报关与采购明细" description="当前报关单尚未返回明细数据。" />
      )}
    </div>
  );
}
