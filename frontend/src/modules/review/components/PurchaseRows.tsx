import { Button } from "../../../shared/components/ui";
import type { PurchaseLine } from "../types";

/**
 * 第三层：报关行对应的子采购订单行。挂在报关行下方的明细行（树形连线标示从属），
 * 每个字段的小标签写在数值上方，不再为每条报关行重复一套表头；浅蓝底表示采购来源。
 */
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
    <ul className="fr-purchase-list" aria-label={`${label}关联子采购订单行`}>
      {lines.map((line) => (
        <li key={line.id} className="fr-purchase-item">
          <dl className="fr-purchase-fields">
            <div>
              <dt>子采购单</dt>
              <dd>
                <strong>{line.child}</strong>
                <small>母单 {line.parent}</small>
              </dd>
            </div>
            <div>
              <dt>供应商</dt>
              <dd>{line.supplier}</dd>
            </div>
            <div>
              <dt>采购品名 / 型号</dt>
              <dd>
                <strong>{line.name}</strong>
                {Boolean(line.model) && <small>{line.model}</small>}
              </dd>
            </div>
            <div className="number">
              <dt>{scope === "order" ? "子单数量" : "本次数量"}</dt>
              <dd>
                <strong>{line.quantity}</strong> {line.unit || "单位未提供"}
              </dd>
            </div>
            <div className="number">
              <dt>采购单价</dt>
              <dd>{line.price}</dd>
            </div>
            <div className="number">
              <dt>{scope === "order" ? "订单金额" : "本次采购金额"}</dt>
              <dd>
                <strong>{line.amount || "未提供"}</strong> {line.currency || "未提供币种"}
              </dd>
            </div>
          </dl>
          <Button aria-label={`查看明细：${line.name} ${line.child}`} onClick={() => selectLine(line)}>
            查看
          </Button>
        </li>
      ))}
    </ul>
  );
}
