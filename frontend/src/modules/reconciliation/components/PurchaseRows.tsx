import { Button } from "../../../shared/components/Button";
import type { PurchaseLine } from "../types";
import { DetailColumns } from "./DetailColumns";

export function PurchaseRows({
  lines,
  label,
  scope = "declared",
  selectLine,
}: {
  lines: PurchaseLine[];
  label: string;
  scope?: "declared" | "order";
  selectLine: (line: PurchaseLine) => void;
}) {
  return (
    <div
      className="fr-purchase-scroll"
      role="region"
      aria-label={`${label}关联子采购订单行，可横向滚动`}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 子采购宽表独立滚动，键盘用户需能聚焦此容器，不能伪装为交互式网格。
      tabIndex={0}
    >
      <table className="fr-purchase-table">
        <caption className="fr-sr-only">{label} 对应的子采购订单行</caption>
        <DetailColumns />
        <thead>
          <tr>
            <th scope="col">子采购单 / 母采购单</th>
            <th scope="col">供应商</th>
            <th scope="col">采购品名 / 型号</th>
            <th scope="col" className="number">
              {scope === "order" ? "子单数量" : "本次数量"}
            </th>
            <th scope="col" className="fr-unit">
              单位
            </th>
            <th scope="col" className="number">
              采购单价
            </th>
            <th scope="col" className="number">
              {scope === "order" ? "订单金额" : "本次采购金额"}
            </th>
            <th scope="col" className="fr-action-head">
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.id}>
              <td>
                <strong>{line.child}</strong>
                <small>母单：{line.parent}</small>
              </td>
              <td>{line.supplier}</td>
              <td>
                <strong>{line.name}</strong>
                {Boolean(line.model) && <small>{line.model}</small>}
              </td>
              <td className="number">
                <strong>{line.quantity}</strong>
              </td>
              <td className="fr-unit">{line.unit || "未提供"}</td>
              <td className="number">{line.price}</td>
              <td className="number">
                <strong>{line.amount || "未提供"}</strong>
                <small>{line.currency || "未提供币种"}</small>
              </td>
              <td className="fr-action">
                <Button aria-label={`查看明细：${line.name} ${line.child}`} onClick={() => selectLine(line)}>
                  查看
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
