import { seriesColor } from "./scale";

/**
 * 环形占比图：中心显示合计，右侧图例显示各项的后端文本（数量或金额、占比）。
 * value 只用于计算弧长；占比等业务数字请由后端提供并放入 text。
 */
export interface DonutSegment {
  key: string;
  label: string;
  value: number;
  text: string;
}

export function DonutChart({
  label,
  segments,
  centerLabel,
  centerValue,
  size = 168,
}: {
  label: string;
  segments: readonly DonutSegment[];
  centerLabel: string;
  centerValue: string;
  size?: number;
}) {
  const stroke = size * 0.16;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const total = segments.reduce((sum, s) => sum + Math.max(0, s.value), 0);
  let offset = 0;
  return (
    <figure className="ui-donut" aria-label={label}>
      <div className="ui-donut__ring" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
          <circle className="ui-donut__track" cx={size / 2} cy={size / 2} r={radius} strokeWidth={stroke} />
          {total > 0 &&
            segments.map((segment, index) => {
              const length = (Math.max(0, segment.value) / total) * circumference;
              const dash = (
                <circle
                  key={segment.key}
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  stroke={seriesColor(index)}
                  strokeWidth={stroke}
                  strokeDasharray={`${Math.max(0, length - 2)} ${circumference}`}
                  strokeDashoffset={-offset}
                  transform={`rotate(-90 ${size / 2} ${size / 2})`}
                />
              );
              offset += length;
              return dash;
            })}
        </svg>
        <span className="ui-donut__center">
          <span>{centerLabel}</span>
          <strong>{centerValue}</strong>
        </span>
      </div>
      <ul className="ui-donut__legend">
        {segments.map((segment, index) => (
          <li key={segment.key}>
            <span>
              <i className="ui-chart__key" style={{ background: seriesColor(index) }} />
              {segment.label}
            </span>
            <strong>{segment.text}</strong>
          </li>
        ))}
      </ul>
    </figure>
  );
}
