/** 半圆仪表：percent 为后端给出的 0–100 展示值，text 为后端文本。用于完成率、转化率等单一比率。 */
export function Gauge({
  percent,
  text,
  label,
  size = 96,
}: {
  percent: number;
  text?: string;
  label: string;
  size?: number;
}) {
  const stroke = 9;
  const radius = (size - stroke) / 2;
  const half = Math.PI * radius;
  const clamped = Math.min(100, Math.max(0, percent));
  const path = `M ${stroke / 2} ${size / 2} A ${radius} ${radius} 0 0 1 ${size - stroke / 2} ${size / 2}`;
  return (
    <span className="ui-gauge" role="img" aria-label={`${label} ${text ?? `${clamped}%`}`}>
      <svg
        width={size}
        height={size / 2 + stroke / 2}
        viewBox={`0 0 ${size} ${size / 2 + stroke / 2}`}
        aria-hidden="true"
      >
        <path className="ui-gauge__track" d={path} strokeWidth={stroke} />
        <path
          className="ui-gauge__value"
          d={path}
          strokeWidth={stroke}
          strokeDasharray={`${(clamped / 100) * half} ${half}`}
        />
      </svg>
      {text && <strong>{text}</strong>}
    </span>
  );
}
