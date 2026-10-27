import type { ReactNode } from "react";
import { compactTick, niceTicks } from "./scale";
import "./horizontal-bar-chart.css";

export interface HorizontalBarItem {
  key: string;
  label: string;
  value: number;
  text: string;
  color?: string;
  note?: ReactNode;
}

/** 数值只用于坐标换算；数量文本与附注由调用方提供。零值不画色条。 */
export function HorizontalBarChart({ label, items }: { label: string; items: HorizontalBarItem[] }) {
  const ticks = niceTicks(Math.max(0, ...items.map((item) => item.value)));
  const maximum = ticks[ticks.length - 1];
  const hasNotes = items.some((item) => item.note != null);
  return (
    <div className={`ui-hbar${hasNotes ? " ui-hbar--notes" : ""}`}>
      <ol className="ui-hbar__rows" aria-label={label}>
        {items.map((item) => (
          <li className="ui-hbar__row" key={item.key}>
            <span className="ui-hbar__label">{item.label}</span>
            <span className="ui-hbar__plot">
              <span
                className="ui-hbar__bar"
                style={{ width: `${(Math.max(0, item.value) / maximum) * 100}%`, background: item.color }}
              />
              <span className="ui-hbar__value">{item.text}</span>
            </span>
            {hasNotes && <span className="ui-hbar__note">{item.note}</span>}
          </li>
        ))}
      </ol>
      <div className="ui-hbar__axis-row" aria-hidden="true">
        <div className="ui-hbar__axis">
          {ticks.map((tick) => (
            <span key={tick} style={{ left: `${(tick / maximum) * 100}%` }}>
              {compactTick(tick)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
