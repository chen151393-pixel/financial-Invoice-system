/** 迷你走势线：只表达趋势形状，不显示坐标；数值来自后端序列。 */
export function Sparkline({
  values,
  tone = "primary",
  width = 96,
  height = 32,
}: {
  values: readonly number[];
  tone?: "primary" | "success" | "danger" | "warning" | "inverse";
  width?: number;
  height?: number;
}) {
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const step = width / Math.max(1, values.length - 1);
  const points = values.map(
    (value, index) =>
      `${(index * step).toFixed(1)},${(height - 3 - ((value - min) / span) * (height - 6)).toFixed(1)}`,
  );
  return (
    <svg
      className="ui-sparkline"
      data-tone={tone}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
    >
      <polyline
        points={points.join(" ")}
        fill="none"
        strokeWidth="1.8"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
