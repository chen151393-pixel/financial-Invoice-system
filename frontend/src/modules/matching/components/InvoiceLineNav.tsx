import { Badge, Card, CardHeader } from "../../../shared/components/ui";
import type { Allocation, InvoiceItem } from "../types/matching";
import { groupAllocations } from "./allocation-groups";

// 整单拆分的多条建议通常同属一张子采购单，导航只列出涉及的单号，逐条内容在右侧查看。
function orderNames(pending: Allocation[]) {
  const names = [...new Set(pending.map((row) => row.purchase?.orderNo || "待核对子采购行"))];
  return names.length > 2 ? `${names.slice(0, 2).join("、")} 等 ${names.length} 张` : names.join("、");
}

/** 同一张发票内切换明细；导航始终保留全部行与历史记录入口。 */
export function InvoiceLineNav({
  items,
  selectedId,
  onSelect,
  busy = false,
}: {
  items: InvoiceItem[];
  selectedId: string;
  onSelect: (id: string) => void;
  busy?: boolean;
}) {
  return (
    <Card className="matching-lines" aria-label="发票明细导航">
      <CardHeader title="发票商品明细" description={`共 ${items.length} 行 · 选择后在右侧逐项比对`} />
      <div className="matching-lines__list">
        {items.map((item) => {
          const { linked, pending } = groupAllocations(item.allocations);
          return (
            <button
              type="button"
              key={item.id}
              className="matching-line"
              disabled={busy}
              aria-current={item.id === selectedId ? "true" : undefined}
              onClick={() => onSelect(item.id)}
            >
              <span className="matching-line__title">
                <strong>
                  第 {item.lineNo || "—"} 行 · {item.item || "未提供品名"}
                </strong>
                <Badge tone={pending.length ? "warning" : linked.length ? "info" : "neutral"}>
                  {!item.active
                    ? "历史明细"
                    : pending.length
                      ? `待处理 ${pending.length}`
                      : linked.length
                        ? `已关联 ${linked.length}`
                        : "无关联"}
                </Badge>
              </span>
              {pending.length > 0 && <small>{orderNames(pending)}</small>}
              <span className="matching-line__amount">
                {item.amount ?? "—"} <small>含税</small>
              </span>
              <small>
                {item.quantity ?? "—"} {item.unit || ""} {item.specification || ""}
              </small>
            </button>
          );
        })}
      </div>
    </Card>
  );
}
