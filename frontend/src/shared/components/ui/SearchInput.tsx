import type { InputHTMLAttributes } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "defaultValue" | "onChange"> & {
  value: string;
  onValueChange: (value: string) => void;
};

/** 批量查询输入：粘贴多行时保留条目边界，查询规则与校验由后端负责。 */
export function SearchInput({ value, onValueChange, ...props }: Props) {
  return (
    <input
      type="search"
      title="支持部分内容搜索；多条用逗号、分号分隔，也可直接粘贴多行"
      {...props}
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
      onPaste={(event) => {
        const pasted = event.clipboardData.getData("text");
        if (!/[\r\n\t]/.test(pasted)) return;
        event.preventDefault();
        const input = event.currentTarget;
        const start = input.selectionStart ?? value.length;
        const end = input.selectionEnd ?? start;
        const inserted = pasted.replace(/[\r\n\t]+/g, ";");
        onValueChange(value.slice(0, start) + inserted + value.slice(end));
        requestAnimationFrame(() =>
          input.setSelectionRange(start + inserted.length, start + inserted.length),
        );
      }}
    />
  );
}
