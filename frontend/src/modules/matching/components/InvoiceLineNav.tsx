import type { InvoiceItem } from "../types/matching";
import { groupAllocations } from "./allocation-groups";

/** 发票行导航：选中后右侧展示该行的关联与建议。 */
export function InvoiceLineNav({
  items,
  selectedId,
  onSelect,
}: {
  items: InvoiceItem[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <section className="matching-panel matching-panel--flush matching-lines" aria-label="发票行">
      <div className="matching-panel__head">
        <h2>发票行（{items.length}）</h2>
      </div>
      <div className="matching-lines__list">
        {items.map((item) => {
          const { linked, pending } = groupAllocations(item.allocations);
          return (
            <button
              type="button"
              key={item.id}
              className="matching-line"
              aria-current={item.id === selectedId ? "true" : undefined}
              onClick={() => onSelect(item.id)}
            >
              <span className="matching-line__title">
                <strong>
                  {item.lineNo}. {item.item ?? "—"}
                </strong>
                {!item.active ? (
                  <span className="matching-tag">历史明细</span>
                ) : pending.length > 0 ? (
                  <span className="matching-tag matching-tag--warn">待处理 {pending.length}</span>
                ) : linked.length > 0 ? (
                  <span className="matching-tag matching-tag--ok">已关联 {linked.length}</span>
                ) : (
                  <span className="matching-tag">无关联</span>
                )}
              </span>
              <small>
                {item.quantity ?? "—"} {item.unit ?? ""} · 含税 {item.amount ?? "—"}
              </small>
            </button>
          );
        })}
      </div>
    </section>
  );
}
