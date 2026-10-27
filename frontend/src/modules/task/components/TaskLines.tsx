import { DifferenceClosure } from "./DifferenceClosure";
import type { ClosureRequest, TaskLine } from "../types/task";

export function TaskLines({
  lines,
  busy = false,
  open = false,
  onClose,
}: {
  lines: TaskLine[];
  busy?: boolean;
  // 详情页的「应开明细与收票进度」卡片默认展开
  open?: boolean;
  onClose?: (lineId: string, body: ClosureRequest) => Promise<boolean>;
}) {
  return (
    <details className="it-source-lines" open={open}>
      <summary>审核冻结的应开明细（{lines.length} 行）</summary>
      <p className="it-help">
        按子采购行开票：数量、单位和含税金额为财务审核通过时冻结的采购口径；已收值由发票比对结果汇总。
      </p>
      <div
        className="it-table-wrap"
        role="region"
        aria-label="应开明细，可横向滚动"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表容器支持键盘聚焦滚动。
        tabIndex={0}
      >
        <table>
          <thead>
            <tr>
              <th>子采购单</th>
              <th>品名 / 规格</th>
              <th>应开数量</th>
              <th>应开金额</th>
              <th>已收数量 / 金额</th>
              <th>待复核数量 / 金额（原口径）</th>
              <th>状态</th>
              {onClose && <th>操作</th>}
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => (
              <tr key={line.id}>
                <td>{line.order || "—"}</td>
                <td>
                  {line.name || "—"}
                  {line.specification && <span className="it-secondary">{line.specification}</span>}
                </td>
                <td>
                  {line.quantity || "—"} {line.unit}
                </td>
                <td>
                  {line.amount || "来源缺失"} {line.amount && line.currency}
                </td>
                <td>
                  {line.receivedQuantity} / {line.receivedAmount}
                </td>
                <td>
                  {line.requiresReview
                    ? `${line.pendingQuantity} / ${line.pendingAmount}（需复核）`
                    : "无待复核占用"}
                </td>
                <td>{line.statusLabel}</td>
                {onClose && (
                  <td>
                    <DifferenceClosure
                      key={`${line.id}:${line.ledgerSha256}`}
                      line={line}
                      busy={busy}
                      onClose={onClose}
                    />
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
