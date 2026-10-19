import { Button } from "../../../shared/components/Button";
import "./workbench-metrics.css";
import type { TodoKind, WorkbenchCounts } from "../types/workbench";

export function WorkbenchMetrics({
  counts,
  selected,
  onSelect,
}: {
  counts: WorkbenchCounts;
  selected: TodoKind;
  onSelect: (kind: TodoKind) => void;
}) {
  const cards = [
    {
      kind: "review" as const,
      label: "待财务核对",
      value: counts.review,
      unit: "张报关单",
      note: `${counts.blocked} 张关联资料待补齐`,
      action: "查看核对待办",
      icon: "✓",
    },
    {
      kind: "matching" as const,
      label: "待比对 / 复核",
      value: counts.matching,
      unit: "项发票待办",
      note: `${counts.reverify} 项已确认分配需复核`,
      action: "查看比对待办",
      icon: "≋",
    },
    {
      kind: "task" as const,
      label: "待开票任务",
      value: counts.task,
      unit: "项任务",
      note: `${counts.preparation} 项待备合同或通知`,
      action: "查看开票待办",
      icon: "▤",
    },
  ];
  return (
    <div className="wb-metrics">
      {cards.map((card) => (
        <Button
          key={card.kind}
          className={`wb-metric wb-metric--${card.kind}`}
          aria-pressed={selected === card.kind}
          onClick={() => onSelect(card.kind)}
        >
          <span className="wb-metric__label">
            {card.label}
            <span className="wb-metric__icon" aria-hidden="true">
              {card.icon}
            </span>
          </span>
          <span className="wb-metric__value">
            <strong>{card.value}</strong>
            <span>{card.unit}</span>
          </span>
          <span className="wb-metric__foot">
            <span>{card.note}</span>
            <span>{card.action} →</span>
          </span>
        </Button>
      ))}
    </div>
  );
}
