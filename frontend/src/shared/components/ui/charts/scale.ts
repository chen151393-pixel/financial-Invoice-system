// 图表坐标换算（仅用于绘图位置与坐标轴刻度），不产生业务金额；提示与图例显示调用方给出的后端文本。
export const seriesColor = (index: number) => `var(--color-chart-${(index % 5) + 1})`;

/** 0 到 max 之间取约 count 个"整齐"刻度。 */
export function niceTicks(max: number, count = 5) {
  if (!(max > 0)) return [0, 1];
  const raw = max / count;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((n) => n * power).find((n) => n >= raw) ?? raw;
  const top = Math.ceil(max / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, index) => index * step);
}

/** 坐标轴的紧凑写法：1.2万、3.5亿；只用于刻度，不用于金额展示。 */
export function compactTick(value: number) {
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${+(value / 1e8).toFixed(1)}亿`;
  if (abs >= 1e4) return `${+(value / 1e4).toFixed(1)}万`;
  return `${+value.toFixed(2)}`;
}
