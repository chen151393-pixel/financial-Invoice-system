import { Link } from "react-router";
import { matchingInvoicePath } from "../../../app/paths";
import { tierLabels, type QueueRow } from "../types/matching";

// 只有后端判定可直接通过（无需说明）的高置信度建议可以勾选批量通过。
export const batchable = (row: QueueRow) =>
  row.allocation.tier === "high" && row.allocation.confirm.allowed && row.allocation.noteReasons.length === 0;

export function QueueTable({
  rows,
  selected,
  onToggle,
  onToggleAll,
}: {
  rows: QueueRow[];
  selected: string[];
  onToggle: (id: string, checked: boolean) => void;
  onToggleAll: (checked: boolean) => void;
}) {
  const candidates = rows.filter(batchable);
  const allChecked = candidates.length > 0 && candidates.every((row) => selected.includes(row.allocation.id));
  return (
    <div
      className="matching-table-wrap"
      role="region"
      aria-label="待审核比对建议，可横向滚动"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 宽表容器支持键盘聚焦滚动。
      tabIndex={0}
    >
      <table className="matching-table matching-table--queue">
        <thead>
          <tr>
            <th scope="col">
              <input
                type="checkbox"
                aria-label="选择本页全部可批量通过的建议"
                disabled={candidates.length === 0}
                checked={allChecked}
                onChange={(event) => onToggleAll(event.target.checked)}
              />
            </th>
            <th scope="col">发票号码 / 销售方</th>
            <th scope="col">发票行</th>
            <th scope="col">子采购单 / 品名</th>
            <th scope="col" className="matching-number">
              分配数量
            </th>
            <th scope="col" className="matching-number">
              含税金额
            </th>
            <th scope="col">置信度</th>
            <th scope="col">审核条件</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const allocation = row.allocation;
            return (
              <tr key={allocation.id}>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`选择建议 ${allocation.id}`}
                    disabled={!batchable(row)}
                    checked={selected.includes(allocation.id)}
                    onChange={(event) => onToggle(allocation.id, event.target.checked)}
                  />
                </td>
                <td>
                  {row.invoiceNumber}
                  <small>{row.seller ?? "—"}</small>
                </td>
                <td>{row.itemName ?? "—"}</td>
                <td>
                  {allocation.purchase?.orderNo || "—"}
                  <small>{allocation.purchase?.item || "—"}</small>
                </td>
                <td className="matching-number">{allocation.quantity}</td>
                <td className="matching-number">{allocation.amount}</td>
                <td>
                  <span className="matching-badge" data-tier={allocation.tier}>
                    {allocation.confidence ?? "—"} · {tierLabels[allocation.tier]}
                  </span>
                </td>
                <td className={allocation.confirm.allowed ? "matching-ok" : "matching-warning"}>
                  {row.anomalies && row.anomalies.length > 0 && (
                    <span className="matching-anomalies" aria-label={`异常：${row.anomalies.join("、")}`}>
                      {row.anomalies.map((name) => (
                        <span key={name} className="matching-anomaly">
                          {name}
                        </span>
                      ))}
                    </span>
                  )}
                  {allocation.noteReasons.length
                    ? `需说明：${allocation.noteReasons.join("、")}`
                    : allocation.confirm.reason}
                </td>
                <td>
                  <Link to={matchingInvoicePath(row.invoiceId)}>审核 →</Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
