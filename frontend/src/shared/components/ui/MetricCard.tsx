import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import { Sparkline } from "./charts/Sparkline";

/**
 * 指标卡：标题、图标、主数值、环比与可选迷你走势。
 * value / delta 由后端给出的文本直接展示，前端不计算；sparkline 只用于画线（数值来自后端序列）。
 * delta.tone 由调用方按业务含义指定（例如待收金额上升是 negative），不按涨跌自动配色；warning 为需要关注（橙）。
 * featured="solid" 为主色实底白字（总览页的头号指标），true 为浅主色底；一屏最多一个。
 */
export interface MetricDelta {
  text: string;
  direction: "up" | "down" | "flat";
  tone: "positive" | "negative" | "warning" | "neutral";
  caption?: string;
}

export function MetricCard({
  label,
  value,
  unit,
  icon,
  delta,
  hint,
  sparkline,
  badge,
  featured,
  selected,
  onSelect,
  footer,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  icon?: IconName;
  delta?: MetricDelta;
  hint?: ReactNode;
  sparkline?: number[];
  // 右上角标签（如处理方），与 icon 二选一，badge 优先
  badge?: ReactNode;
  // 主指标：true 为浅主色底，"solid" 为主色实底白字；一屏最多一个
  featured?: boolean | "solid";
  // 作为筛选入口时使用：渲染为按钮并以 aria-pressed 表示选中
  selected?: boolean;
  onSelect?: () => void;
  footer?: ReactNode;
}) {
  const body = (
    <>
      <span className="ui-metric__top">
        <span className="ui-metric__label">{label}</span>
        {badge ? (
          <span className="ui-metric__badge">{badge}</span>
        ) : (
          icon && (
            <span className="ui-metric__icon">
              <Icon name={icon} />
            </span>
          )
        )}
      </span>
      <span className="ui-metric__value">
        <strong>{value}</strong>
        {unit && <span>{unit}</span>}
      </span>
      <span className="ui-metric__bottom">
        <span className="ui-metric__meta">
          {delta && (
            <span className="ui-metric__delta" data-tone={delta.tone}>
              {delta.direction !== "flat" && (
                <Icon name={delta.direction === "up" ? "trendUp" : "trendDown"} />
              )}
              {delta.text}
              {delta.caption && <span>{delta.caption}</span>}
            </span>
          )}
          {hint && <span className="ui-metric__hint">{hint}</span>}
        </span>
        {sparkline && sparkline.length > 1 && (
          <Sparkline
            values={sparkline}
            tone={
              featured === "solid"
                ? "inverse"
                : delta?.tone === "negative"
                  ? "danger"
                  : delta?.tone === "warning"
                    ? "warning"
                    : "primary"
            }
          />
        )}
      </span>
      {footer}
    </>
  );
  const className = featured
    ? `ui-metric ui-metric--featured${featured === "solid" ? " ui-metric--solid" : ""}`
    : "ui-metric";
  return onSelect ? (
    <button type="button" className={className} aria-pressed={Boolean(selected)} onClick={onSelect}>
      {body}
    </button>
  ) : (
    <div className={className}>{body}</div>
  );
}

/** 指标卡栅格：自动换行，桌面一行 4–6 张。 */
export function MetricGrid({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <div className="ui-metric-grid" role={label ? "group" : undefined} aria-label={label}>
      {children}
    </div>
  );
}
