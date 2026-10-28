import type { FormEvent, ReactNode } from "react";

/**
 * 查询条件栏：标签在上、控件在下，查询按钮靠近条件。
 * 输入框、下拉框直接写原生 input / select，样式由 .ui-filter-bar 统一；条件修改后未提交时用 pending 提示。
 */
export function FilterBar({
  onSubmit,
  children,
  actions,
  pending,
  embedded,
}: {
  // 提交时传入表单元素，需要用 FormData 取值（非受控输入）的页面可直接读取
  onSubmit: (form: HTMLFormElement) => void;
  children: ReactNode;
  actions: ReactNode;
  pending?: string;
  // 放在卡片内部（列表卡片的标题下方）时去掉自身边框，只保留分隔线
  embedded?: boolean;
}) {
  return (
    <form
      className={embedded ? "ui-filter-bar ui-filter-bar--embedded" : "ui-filter-bar"}
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        onSubmit(event.currentTarget);
      }}
    >
      {children}
      <div className="ui-filter-bar__actions">{actions}</div>
      {pending && (
        <span className="ui-filter-bar__pending" role="status">
          {pending}
        </span>
      )}
    </form>
  );
}

/** 条件字段：默认显示中文标签；hideLabel 仅视觉隐藏，保留读屏名称。 */
export function Field({
  label,
  children,
  grow,
  hideLabel = false,
}: {
  label: string;
  children: ReactNode;
  grow?: boolean;
  hideLabel?: boolean;
}) {
  return (
    <label className={grow ? "ui-field ui-field--grow" : "ui-field"}>
      <span className={hideLabel ? "ui-sr-only" : undefined}>{label}</span>
      {children}
    </label>
  );
}
