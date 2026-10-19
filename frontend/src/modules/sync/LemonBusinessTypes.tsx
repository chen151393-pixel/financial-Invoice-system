type Props = {
  options: string[];
  selected: string[];
  disabled: boolean;
  onChange: (values: string[]) => void;
};

export function LemonBusinessTypes({ options, selected, disabled, onChange }: Props) {
  const choices = [...new Set([...options, ...selected])];
  return (
    <fieldset className="lemon-invoices__types" disabled={disabled} aria-describedby="lemon-types-help">
      <legend>保存的业务类型（可多选）</legend>
      <div className="lemon-invoices__type-options">
        {choices.map((value) => (
          <label key={value} className="lemon-invoices__type-option">
            <input
              type="checkbox"
              name="businessTypes"
              value={value}
              checked={selected.includes(value)}
              onChange={(event) =>
                onChange(
                  event.target.checked ? [...selected, value] : selected.filter((item) => item !== value),
                )
              }
            />
            {value}
          </label>
        ))}
      </div>
      <p id="lemon-types-help" className="lemon-invoices__note">
        至少选择一项。其他类型会在拉取后补充到选项中；未勾选的类型跳过，不删除已入库发票。
      </p>
    </fieldset>
  );
}
