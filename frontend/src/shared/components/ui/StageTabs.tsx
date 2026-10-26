import type { ReactNode } from "react";

/**
 * 流程分区条：按流程顺序横排各阶段（数量 + 说明），阶段之间以箭头连接，点击按阶段筛选。
 * 左侧可放合计入口（如"进行中"）。数量与说明由后端给出；窄屏自动换行为两列。
 */
export interface StageItem<K extends string> {
  key: K;
  label: string;
  count: number;
  hint?: string;
  // 终态（如已完成）不画流程箭头，与前面的阶段隔开
  terminal?: boolean;
}

export function StageTabs<K extends string>({
  label,
  items,
  value,
  total,
  onChange,
}: {
  label: string;
  items: readonly StageItem<K>[];
  value: K | "";
  total?: { label: string; count: number; hint?: ReactNode };
  onChange: (key: K | "") => void;
}) {
  return (
    <div className="ui-stages" role="group" aria-label={label}>
      {total && (
        <button
          type="button"
          className="ui-stages__total"
          aria-pressed={value === ""}
          onClick={() => onChange("")}
        >
          <span className="ui-stages__label">{total.label}</span>
          <strong>{total.count}</strong>
          {total.hint && <span className="ui-stages__hint">{total.hint}</span>}
        </button>
      )}
      <ol className="ui-stages__list">
        {items.map((item, index) => (
          <li key={item.key} data-terminal={item.terminal || undefined}>
            <button
              type="button"
              className="ui-stages__item"
              aria-pressed={value === item.key}
              data-empty={item.count === 0 || undefined}
              onClick={() => onChange(item.key)}
            >
              <span className="ui-stages__label">
                <b aria-hidden="true">{item.terminal ? "✓" : index + 1}</b>
                {item.label}
              </span>
              <strong>{item.count}</strong>
              {item.hint && <span className="ui-stages__hint">{item.hint}</span>}
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
