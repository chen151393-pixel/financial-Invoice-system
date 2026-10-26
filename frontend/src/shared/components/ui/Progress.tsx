import type { Tone } from "./Badge";

/**
 * 进度条：width 为后端给出的 0–100 展示宽度（如 receiptBarPercent），text 为后端给出的实际值文本（可能超过 100%）。
 * 前端不计算百分比。
 */
export function Progress({
  width,
  text,
  label,
  tone = "info",
}: {
  width: string | number;
  text?: string;
  label: string;
  tone?: Extract<Tone, "info" | "success" | "progress" | "warning">;
}) {
  return (
    <span className="ui-progress" data-tone={tone}>
      <span
        className="ui-progress__track"
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Number(width)}
        aria-valuetext={text}
      >
        <span style={{ width: `${width}%` }} />
      </span>
      {text && <span className="ui-progress__text">{text}</span>}
    </span>
  );
}
