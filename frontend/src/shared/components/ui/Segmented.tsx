/** 分段选择（2–7 个互斥选项，如"近 7 天 / 近 30 天"、节点切换）。选项与计数由调用方传入。 */
export function Segmented<V extends string>({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: V;
  options: readonly { value: V; label: string; count?: number }[];
  disabled?: boolean;
  onChange: (value: V) => void;
}) {
  return (
    <div className="ui-segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          disabled={disabled}
          onClick={() => onChange(option.value)}
        >
          {option.label}
          {option.count !== undefined && <span className="ui-segmented__count">{option.count}</span>}
        </button>
      ))}
    </div>
  );
}
