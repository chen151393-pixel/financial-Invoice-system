import type { Conversion } from "../types/matching";
export const defaultConversion: Conversion = {
  conversionNumerator: "1",
  conversionDenominator: "1",
  conversionEvidence: "",
};
export function ConversionFields({
  value,
  onChange,
  busy,
}: {
  value: Conversion;
  onChange: (value: Conversion) => void;
  busy: boolean;
}) {
  return (
    <fieldset disabled={busy} className="matching-form">
      <legend>数量口径核实</legend>
      <p className="matching-help">
        采购数量 = 发票数量 × 分子 ÷ 分母。同单位使用 1 / 1；不同单位请填写该商品的换算证据。
      </p>
      <div className="matching-row">
        <label>
          换算分子
          <input
            inputMode="decimal"
            value={value.conversionNumerator}
            onChange={(e) => onChange({ ...value, conversionNumerator: e.target.value })}
          />
        </label>
        <label>
          换算分母
          <input
            inputMode="decimal"
            value={value.conversionDenominator}
            onChange={(e) => onChange({ ...value, conversionDenominator: e.target.value })}
          />
        </label>
      </div>
      <label>
        换算证据
        <input
          value={value.conversionEvidence}
          onChange={(e) => onChange({ ...value, conversionEvidence: e.target.value })}
        />
      </label>
    </fieldset>
  );
}
