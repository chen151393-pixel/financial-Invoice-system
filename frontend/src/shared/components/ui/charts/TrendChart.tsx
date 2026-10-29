import { useEffect, useRef, useState } from "react";
import { compactTick, niceTicks, seriesColor } from "./scale";

/**
 * 趋势图：堆叠柱（或 grouped 并排柱）+ 可选折线，悬停显示该类目各系列。
 * values 只用于绘图；texts 为后端给出的展示文本（金额请传后端十进制字符串格式化后的结果），缺省时显示刻度写法。
 * line 的 null 值保留断点。百分比轴上限至少 100%，按实际最大值扩展；“—”不标注。
 * 无负数场景使用；含负金额的序列请用专门的正负柱表达。
 */
export interface ChartSeries {
  key: string;
  label: string;
  values: readonly number[];
  texts?: readonly string[];
  // 系列颜色（设计变量），缺省按顺序取图表配色
  color?: string;
}

export interface ChartLineSeries extends Omit<ChartSeries, "values"> {
  // null 表示没有可统计值；保留断点，不按 0 绘制或跨越连接。
  values: readonly (number | null)[];
}

const PAD = { top: 16, right: 12, bottom: 28, left: 48 };

export function TrendChart({
  label,
  categories,
  bars = [],
  line,
  grouped = false,
  lineAxis = "shared",
  height = 260,
}: {
  label: string;
  categories: readonly string[];
  bars?: readonly ChartSeries[];
  line?: ChartLineSeries;
  grouped?: boolean;
  lineAxis?: "shared" | "percent";
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  const [active, setActive] = useState<number | null>(null);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const percent = lineAxis === "percent" && Boolean(line);
  const right = percent ? 40 : PAD.right;
  const totals = categories.map((_, i) =>
    grouped
      ? Math.max(0, ...bars.map((s) => s.values[i] ?? 0))
      : bars.reduce((sum, s) => sum + Math.max(0, s.values[i] ?? 0), 0),
  );
  const lineValues = line?.values.filter((value): value is number => value !== null) ?? [];
  const percentTop = niceTicks(Math.max(100, ...lineValues)).at(-1) ?? 100;
  const percentTicks = [0, percentTop / 2, percentTop];
  const ticks = niceTicks(Math.max(...totals, ...(percent ? [] : lineValues), 0));
  const top = ticks[ticks.length - 1];
  const innerW = width - PAD.left - right;
  const innerH = height - PAD.top - PAD.bottom;
  const slot = innerW / Math.max(1, categories.length);
  const barW = grouped ? Math.min(22, (slot * 0.7) / Math.max(1, bars.length)) : Math.min(28, slot * 0.5);
  const y = (value: number) => PAD.top + innerH - (value / top) * innerH;
  const lineY = (value: number) =>
    percent ? PAD.top + innerH - (Math.max(0, value) / percentTop) * innerH : y(value);
  const x = (index: number) => PAD.left + slot * index + slot / 2;
  const color = (series: Pick<ChartSeries, "color">, index: number) => series.color ?? seriesColor(index);
  const every = Math.ceil(categories.length / Math.max(1, Math.floor(innerW / 56)));
  const all = [...bars, ...(line ? [line] : [])];
  const text = (series: ChartSeries | ChartLineSeries, i: number) =>
    series.texts?.[i] ?? (series.values[i] == null ? "—" : compactTick(series.values[i]));
  const segments: string[][] = [];
  line?.values.forEach((value, i) => {
    if (value === null) return;
    if (i === 0 || line.values[i - 1] === null) segments.push([]);
    segments[segments.length - 1].push(`${x(i)},${lineY(value)}`);
  });

  return (
    <figure className="ui-chart" aria-label={label}>
      <figcaption className="ui-chart__legend">
        {line && (
          <span>
            <i className="ui-chart__key ui-chart__key--line" />
            {line.label}
          </span>
        )}
        {bars.map((series, index) => (
          <span key={series.key}>
            <i className="ui-chart__key" style={{ background: color(series, index) }} />
            {series.label}
          </span>
        ))}
      </figcaption>
      {/* 画布高度固定、SVG 绝对定位，宽度只跟随容器，不反过来撑宽页面 */}
      <div className="ui-chart__canvas" ref={ref} style={{ height }} onMouseLeave={() => setActive(null)}>
        <svg width={width} height={height} role="img" aria-label={label}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line className="ui-chart__grid" x1={PAD.left} x2={width - right} y1={y(tick)} y2={y(tick)} />
              <text className="ui-chart__axis" x={PAD.left - 8} y={y(tick) + 4} textAnchor="end">
                {compactTick(tick)}
              </text>
            </g>
          ))}
          {percent &&
            percentTicks.map((tick) => (
              <text key={tick} className="ui-chart__axis" x={width - right + 8} y={lineY(tick) + 4}>
                {tick}%
              </text>
            ))}
          {categories.map((category, i) => {
            let base = 0;
            return (
              <g
                key={category}
                tabIndex={0}
                role="group"
                aria-label={`${category}，${all.map((series) => `${series.label} ${text(series, i)}`).join("，")}`}
                onMouseEnter={() => setActive(i)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
              >
                <rect
                  className="ui-chart__hit"
                  x={x(i) - slot / 2}
                  y={PAD.top}
                  width={slot}
                  height={innerH}
                  data-active={active === i || undefined}
                />
                {bars.map((series, index) => {
                  const value = Math.max(0, series.values[i] ?? 0);
                  if (grouped) {
                    const left = x(i) - (barW * bars.length) / 2 + index * barW;
                    return (
                      <rect
                        key={series.key}
                        x={left + 1}
                        y={y(value)}
                        width={Math.max(1, barW - 2)}
                        height={Math.max(0, y(0) - y(value))}
                        rx={3}
                        fill={color(series, index)}
                      />
                    );
                  }
                  const y0 = y(base);
                  base += value;
                  const last = index === bars.length - 1;
                  return (
                    <rect
                      key={series.key}
                      x={x(i) - barW / 2}
                      y={y(base)}
                      width={barW}
                      height={Math.max(0, y0 - y(base))}
                      rx={last ? 3 : 0}
                      fill={color(series, index)}
                    />
                  );
                })}
                {(i === categories.length - 1 ||
                  (i % every === 0 && (i === 0 || x(categories.length - 1) - x(i) >= 56))) && (
                  <text className="ui-chart__axis" x={x(i)} y={height - 8} textAnchor="middle">
                    {category}
                  </text>
                )}
              </g>
            );
          })}
          {line && (
            <g className="ui-chart__series-line">
              {segments.map(
                (points, i) =>
                  points.length > 1 && (
                    <polyline key={i} className="ui-chart__line" points={points.join(" ")} />
                  ),
              )}
              {line.values.map((value, i) =>
                value === null ? null : (
                  <circle
                    key={categories[i]}
                    className="ui-chart__point"
                    cx={x(i)}
                    cy={lineY(value)}
                    r={active === i ? 4.5 : 3}
                  />
                ),
              )}
              {percent &&
                line.texts?.map((text, i) =>
                  text === "—" || line.values[i] == null ? null : (
                    <text
                      key={categories[i]}
                      className="ui-chart__point-label"
                      x={x(i)}
                      y={lineY(line.values[i] ?? 0) - 8}
                      textAnchor="middle"
                    >
                      {text}
                    </text>
                  ),
                )}
            </g>
          )}
        </svg>
        {active !== null && (
          <div
            className="ui-chart__tooltip"
            style={{ left: Math.min(Math.max(x(active), 90), width - 90), top: 8 }}
            role="status"
          >
            <strong>{categories[active]}</strong>
            {all.map((series, index) => (
              <span key={series.key}>
                <i
                  className="ui-chart__key"
                  style={{ background: series === line ? "var(--color-chart-line)" : color(series, index) }}
                />
                {series.label}
                <b>{text(series, active)}</b>
              </span>
            ))}
          </div>
        )}
      </div>
      {/* 读屏与键盘用户的等价数据 */}
      <div className="ui-sr-only">
        <table>
          <caption>{label}</caption>
          <thead>
            <tr>
              <th scope="col">日期</th>
              {all.map((series) => (
                <th key={series.key} scope="col">
                  {series.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {categories.map((category, i) => (
              <tr key={category}>
                <th scope="row">{category}</th>
                {all.map((series) => (
                  <td key={series.key}>{text(series, i)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </figure>
  );
}
