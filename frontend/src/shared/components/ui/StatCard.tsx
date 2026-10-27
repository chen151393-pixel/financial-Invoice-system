import type { CSSProperties, ReactNode } from "react";

export type StatTone = "neutral" | "warning" | "primary";

/**
 * 概况卡：一个字的图块 + 标签 + 数值 + 一句说明（财务核对、开票跟进等页顶部的概况）。
 * 数值与说明由后端给出的文本直接展示，前端不计算；tone 由调用方按业务含义指定。
 * compact 用于一行排开较多卡片（图块与标签同行，数值与说明在下）。
 */
export function StatCard({
  glyph,
  label,
  value,
  note,
  tone = "neutral",
  compact,
  selected,
  onSelect,
}: {
  glyph: string;
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: StatTone;
  compact?: boolean;
  // 作为筛选入口时使用：渲染为按钮并以 aria-pressed 表示选中
  selected?: boolean;
  onSelect?: () => void;
}) {
  const className = compact ? "ui-stat ui-stat--compact" : "ui-stat";
  const tile = (
    <span className="ui-stat__glyph" data-tone={tone} aria-hidden="true">
      {glyph}
    </span>
  );
  const body = compact ? (
    <>
      <span className="ui-stat__head">
        {tile}
        <span className="ui-stat__label">{label}</span>
      </span>
      <strong className="ui-stat__value">{value}</strong>
      {note && (
        <span className="ui-stat__note" data-tone={tone}>
          {note}
        </span>
      )}
    </>
  ) : (
    <>
      {tile}
      <span className="ui-stat__text">
        <span className="ui-stat__label">{label}</span>
        <strong className="ui-stat__value">{value}</strong>
        {note && (
          <span className="ui-stat__note" data-tone={tone}>
            {note}
          </span>
        )}
      </span>
    </>
  );
  return onSelect ? (
    <button type="button" className={className} aria-pressed={Boolean(selected)} onClick={onSelect}>
      {body}
    </button>
  ) : (
    <div className={className}>{body}</div>
  );
}

/** 概况卡栅格：按最小列宽自动换行；min 越小一行放得越多。 */
export function StatGrid({
  children,
  label,
  min = 200,
}: {
  children: ReactNode;
  label?: string;
  min?: number;
}) {
  return (
    <div
      className="ui-stat-grid"
      role={label ? "group" : undefined}
      aria-label={label}
      style={{ "--ui-stat-min": `${min}px` } as CSSProperties}
    >
      {children}
    </div>
  );
}
