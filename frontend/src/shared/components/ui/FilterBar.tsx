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
}: {
  // 提交时传入表单元素，需要用 FormData 取值（非受控输入）的页面可直接读取
  onSubmit: (form: HTMLFormElement) => void;
  children: ReactNode;
  actions: ReactNode;
  pending?: string;
}) {
  return (
    <form
      className="ui-filter-bar"
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

/** 条件字段：持续可见的中文标签；grow 用于关键字等需要更宽的输入。 */
export function Field({ label, children, grow }: { label: string; children: ReactNode; grow?: boolean }) {
  return (
    <label className={grow ? "ui-field ui-field--grow" : "ui-field"}>
      <span>{label}</span>
      {children}
    </label>
  );
}
