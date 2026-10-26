/**
 * 下划线标签：同一区域内切换视图或状态筛选（如 全部 / 待审核 / 审核通过），可带计数。
 * 计数由后端给出；选中以 aria-pressed 表示，不改变地址时用作筛选按钮组。
 */
export function Tabs<K extends string>({
  label,
  items,
  value,
  onChange,
}: {
  label: string;
  items: readonly { key: K; label: string; count?: number }[];
  value: K;
  onChange: (key: K) => void;
}) {
  return (
    <div className="ui-tabs" role="group" aria-label={label}>
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          aria-pressed={item.key === value}
          onClick={() => onChange(item.key)}
        >
          {item.label}
          {item.count !== undefined && <span className="ui-tabs__count">{item.count}</span>}
        </button>
      ))}
    </div>
  );
}
