/**
 * 流程节点：已完成 ✓、当前节点高亮、未开始灰色；状态由后端判定，组件只展示。
 * compact 用于列表行内；传 onSelect 时每个节点可点击（如详情页按节点切换内容分区），selectedKey 为当前查看的节点。
 */
export interface StepItem {
  key: string;
  label: string;
  description?: string;
  state: "done" | "current" | "waiting";
}

const STATE_TEXT = { done: "已完成", current: "当前节点", waiting: "未开始" } as const;

export function Stepper({
  steps,
  label,
  compact,
  selectedKey,
  onSelect,
}: {
  steps: readonly StepItem[];
  label: string;
  compact?: boolean;
  selectedKey?: string;
  onSelect?: (key: string) => void;
}) {
  return (
    <ol
      className={compact ? "ui-stepper ui-stepper--compact" : "ui-stepper"}
      aria-label={label}
      style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}
    >
      {steps.map((step, index) => {
        const body = (
          <>
            <span className="ui-stepper__dot" aria-hidden="true">
              {step.state === "done" ? "✓" : index + 1}
            </span>
            <span className="ui-stepper__label">
              {step.label}
              <span className="ui-sr-only">（{STATE_TEXT[step.state]}）</span>
            </span>
            {step.description && (
              <span className="ui-stepper__desc" title={step.description}>
                {step.description}
              </span>
            )}
          </>
        );
        return (
          <li
            key={step.key}
            data-state={step.state}
            aria-current={step.state === "current" ? "step" : undefined}
          >
            {onSelect ? (
              <button
                type="button"
                className="ui-stepper__button"
                aria-pressed={selectedKey === step.key}
                onClick={() => onSelect(step.key)}
              >
                {body}
              </button>
            ) : (
              body
            )}
          </li>
        );
      })}
    </ol>
  );
}
