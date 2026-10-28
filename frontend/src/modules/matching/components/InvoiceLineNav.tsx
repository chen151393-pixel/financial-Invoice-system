import { Badge, Card, CardHeader } from "../../../shared/components/ui";
import type { InvoiceItem } from "../types/matching";
import { groupAllocations } from "./allocation-groups";

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
      <CardHeader title="发票明细" description={`共 ${items.length} 行 · 逐行核对建议`} />
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
              {pending.map((allocation) => (
                <small key={allocation.id}>
                  {allocation.purchase?.orderNo || "待核对子采购行"} · {allocation.confidence ?? "—"}%
                </small>
              ))}
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
