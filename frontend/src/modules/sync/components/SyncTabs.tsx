export const syncTabs = [
  ["manual", "手动补拉"],
  ["plan", "定时计划"],
] as const;
export type SyncTab = (typeof syncTabs)[number][0];

/** “手动补拉 / 定时计划”页签（NS 与柠檬云共用）；处理中禁止切换，避免中途离开正在提交的表单。 */
export function SyncTabs({
  value,
  onChange,
  disabled,
}: {
  value: SyncTab;
  onChange: (value: SyncTab) => void;
  disabled: boolean;
}) {
  return (
    <div className="sync-tabs" role="group" aria-label="同步配置方式">
      {syncTabs.map(([key, label]) => (
        <button
          type="button"
          key={key}
          className="sync-tab"
          aria-pressed={value === key}
          disabled={disabled}
          onClick={() => onChange(key)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
