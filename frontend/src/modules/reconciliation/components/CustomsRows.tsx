import { DetailColumns } from "./DetailColumns";
import { PurchaseRows } from "./PurchaseRows";
import type { ComparisonGroup as Group, PurchaseLine as Line } from "../types";
import { FinanceIcon as Icon } from "./FinanceIcon";

export function CustomsRows({
  group,
  expandedRows,
  toggleRow,
  selectLine,
}: {
  group: Group;
  expandedRows: string[];
  toggleRow: (id: string) => void;
  selectLine: (line: Line) => void;
}) {
  return (
    <div
      className="fr-table-scroll"
      role="region"
      aria-label={`${group.recordNumber} 报关行，可横向滚动`}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表格需要键盘聚焦后用方向键滚动，保持内部原生表格语义，与正式核对页一致。
      tabIndex={0}
    >
      <table className="fr-customs-table">
        <caption className="fr-sr-only">
          {group.recordNumber} 的报关明细，展开品名查看对应子采购订单行
        </caption>
        <DetailColumns />
        <thead>
          <tr>
            <th scope="col" colSpan={2} className="fr-toggle-heading">
              报关行 / 商品品名
            </th>
            <th scope="col">规格型号</th>
            <th scope="col" className="number">
              申报数量
            </th>
            <th scope="col" className="fr-unit">
              单位
            </th>
            <th scope="col" className="number">
              申报单价
            </th>
            <th scope="col" className="number">
              报关金额
            </th>
            <th scope="col">关联采购</th>
          </tr>
        </thead>
        {group.customsLines.map((row) => {
          const expanded = expandedRows.includes(row.id);
          const canExpand = row.purchaseCount > 0;
          const label = (
            <>
              <span className={`fr-chevron ${expanded ? "open" : ""}`} aria-hidden="true">
                {canExpand && <Icon kind="chevron" />}
              </span>
              <span className="fr-line-number">{row.lineNo}</span>
              <strong>{row.name}</strong>
            </>
          );
          return (
            <tbody key={row.id}>
              <tr className={`fr-customs-row ${expanded ? "is-expanded" : ""}`}>
                <th scope="row" colSpan={2}>
                  {canExpand ? (
                    <button
                      className="fr-row-toggle"
                      aria-expanded={expanded}
                      aria-controls={`purchases-${group.id}-${row.id}`}
                      aria-label={`${expanded ? "收起" : "展开"}报关行：${row.name}（${group.recordNumber} 第 ${row.lineNo} 行）`}
                      onClick={() => toggleRow(row.id)}
                    >
                      {label}
                    </button>
                  ) : (
                    <div className="fr-row-label">{label}</div>
                  )}
                </th>
                <td>{row.model}</td>
                <td className="number">{row.quantity || "未提供"}</td>
                <td className="fr-unit">{row.unit || "未提供"}</td>
                <td className="number">{row.price || "未提供"}</td>
                <td className="number">
                  <strong>{row.amount}</strong>
                  <small>{row.currency || "未提供币种"}</small>
                </td>
                <td>
                  <span className="fr-related-count">{row.purchaseCount} 条子采购行</span>
                </td>
              </tr>
              {row.purchaseCount > 0 && (
                <tr hidden={!expanded} id={`purchases-${group.id}-${row.id}`} className="fr-expanded-row">
                  <td colSpan={8}>
                    <div className="fr-purchases">
                      <PurchaseRows
                        lines={row.purchaseLines}
                        label={row.name}
                        scope={row.purchaseLines[0]?.scope ?? "declared"}
                        selectLine={selectLine}
                      />
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}
