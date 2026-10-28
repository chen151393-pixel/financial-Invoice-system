import type { CSSProperties, ReactNode } from "react";

/**
 * 数据表：浅色表头、行悬停、数值列右对齐等宽数字；宽表在自身容器内横向滚动。
 * 排序、分页、筛选由后端提供，组件不在前端重排或汇总。
 */
export interface Column<Row> {
  key: string;
  header: ReactNode;
  render: (row: Row) => ReactNode;
  align?: "left" | "right" | "center";
  width?: string;
}

export function DataTable<Row>({
  label,
  columns,
  rows,
  rowKey,
  minWidth = 720,
  density = "default",
  rowTone,
  maxHeight,
}: {
  label: string;
  columns: readonly Column<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row) => string;
  minWidth?: number;
  density?: "default" | "compact";
  rowTone?: (row: Row) => "accent" | undefined;
  /** 限高后在表内上下滚动，并固定表头。 */
  maxHeight?: CSSProperties["maxHeight"];
}) {
  return (
    <div
      className="ui-table-scroll"
      data-bounded={maxHeight !== undefined || undefined}
      style={maxHeight !== undefined ? { maxHeight } : undefined}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 键盘用户需要聚焦容器来横向滚动宽表。
      tabIndex={0}
      role="region"
      aria-label={`${label}，${maxHeight !== undefined ? "可上下及横向滚动" : "可横向滚动"}`}
    >
      <table className="ui-table" data-density={density} style={{ minWidth }}>
        <colgroup>
          {columns.map((column) => (
            <col key={column.key} style={column.width ? { width: column.width } : undefined} />
          ))}
        </colgroup>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" data-align={column.align}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} data-tone={rowTone?.(row)}>
              {columns.map((column) => (
                <td key={column.key} data-align={column.align}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
