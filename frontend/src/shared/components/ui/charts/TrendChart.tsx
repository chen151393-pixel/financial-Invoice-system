import { useEffect, useRef, useState } from "react";
import { compactTick, niceTicks, seriesColor } from "./scale";

/**
 * 趋势图：堆叠柱 + 可选折线（参考图 GMV Trend 的形式），悬停显示该日各系列。
 * values 只用于绘图；texts 为后端给出的展示文本（金额请传后端十进制字符串格式化后的结果），缺省时显示刻度写法。
 * 无负数场景使用；含负金额的序列请用专门的正负柱表达。
 */
export interface ChartSeries {
  key: string;
  label: string;
  values: readonly number[];
  texts?: readonly string[];
}

const PAD = { top: 16, right: 12, bottom: 28, left: 48 };

export function TrendChart({
  label,
  categories,
  bars = [],
  line,
  height = 260,
}: {
  label: string;
  categories: readonly string[];
  bars?: readonly ChartSeries[];
  line?: ChartSeries;
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

  const totals = categories.map((_, i) => bars.reduce((sum, s) => sum + Math.max(0, s.values[i] ?? 0), 0));
  const ticks = niceTicks(Math.max(...totals, ...(line?.values ?? [0]), 0));
  const top = ticks[ticks.length - 1];
  const innerW = width - PAD.left - PAD.right;
  const innerH = height - PAD.top - PAD.bottom;
  const slot = innerW / Math.max(1, categories.length);
  const barW = Math.min(28, slot * 0.5);
  const y = (value: number) => PAD.top + innerH - (value / top) * innerH;
  const x = (index: number) => PAD.left + slot * index + slot / 2;
  const every = Math.ceil(categories.length / Math.max(1, Math.floor(innerW / 56)));
  const all = [...bars, ...(line ? [line] : [])];
  const text = (series: ChartSeries, i: number) => series.texts?.[i] ?? compactTick(series.values[i] ?? 0);

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
            <i className="ui-chart__key" style={{ background: seriesColor(index) }} />
            {series.label}
          </span>
        ))}
      </figcaption>
      {/* 画布高度固定、SVG 绝对定位，宽度只跟随容器，不反过来撑宽页面 */}
      <div className="ui-chart__canvas" ref={ref} style={{ height }} onMouseLeave={() => setActive(null)}>
        <svg width={width} height={height} role="img" aria-label={label}>
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                className="ui-chart__grid"
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(tick)}
                y2={y(tick)}
              />
              <text className="ui-chart__axis" x={PAD.left - 8} y={y(tick) + 4} textAnchor="end">
                {compactTick(tick)}
              </text>
            </g>
          ))}
          {categories.map((category, i) => {
            let base = 0;
            return (
              <g key={category} onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)}>
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
                      fill={seriesColor(index)}
                    />
                  );
                })}
                {i % every === 0 && (
                  <text className="ui-chart__axis" x={x(i)} y={height - 8} textAnchor="middle">
                    {category}
                  </text>
                )}
              </g>
            );
          })}
          {line && (
            <g className="ui-chart__series-line">
              <polyline
                className="ui-chart__line"
                points={line.values.map((value, i) => `${x(i)},${y(value)}`).join(" ")}
              />
              {line.values.map((value, i) => (
                <circle
                  key={categories[i]}
                  className="ui-chart__point"
                  cx={x(i)}
                  cy={y(value)}
                  r={active === i ? 4.5 : 3}
                />
              ))}
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
                  style={{ background: series === line ? "var(--color-chart-line)" : seriesColor(index) }}
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
