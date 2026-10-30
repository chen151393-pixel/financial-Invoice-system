import type { ReactNode } from "react";
import { Button } from "../../../shared/components/Button";

export type ScheduleValue = { enabled: boolean; times: string[]; lookbackDays: number };

type Props = {
  value: ScheduleValue;
  change: (value: Partial<ScheduleValue>) => void;
  disabled: boolean;
  /** 回扫天数单位前的日期口径，如“创建日期”“开票日期”。 */
  dateLabel: string;
  lookbackHint: ReactNode;
};

/**
 * 每日定时计划的公共字段（柠檬云与 NS 计划共用）：是否启用、北京时间执行时点、回扫天数。
 * 已保存的启用状态与下次执行显示在页面状态条，这里只编辑；校验由后端完成。
 */
export function SyncScheduleFields({ value, change, disabled, dateLabel, lookbackHint }: Props) {
  return (
    <>
      <fieldset disabled={disabled} className="sync-background__scope">
        <legend>何时执行（北京时间）</legend>
        <label className="sync-background__switch">
          <input
            type="checkbox"
            checked={value.enabled}
            onChange={(event) => change({ enabled: event.target.checked })}
          />
          启用定时同步
        </label>
        <div className="sync-background__inline">
          {value.times.map((time, index) => (
            <span className="sync-time" key={index}>
              <input
                aria-label={`执行时间 ${index + 1}`}
                type="time"
                value={time}
                onChange={(event) =>
                  change({ times: value.times.map((item, i) => (i === index ? event.target.value : item)) })
                }
              />
              <button
                type="button"
                aria-label={`移除执行时间 ${time}`}
                onClick={() => change({ times: value.times.filter((_, i) => i !== index) })}
              >
                ×
              </button>
            </span>
          ))}
          <Button onClick={() => change({ times: [...value.times, "14:00"] })}>＋ 添加执行时间</Button>
        </div>
      </fieldset>
      <fieldset disabled={disabled} className="sync-background__scope">
        <legend>每次回扫</legend>
        <label>
          最近
          <input
            type="number"
            value={value.lookbackDays}
            onChange={(event) => change({ lookbackDays: Number(event.target.value) })}
          />
          天的{dateLabel}
        </label>
        <p>{lookbackHint}</p>
      </fieldset>
    </>
  );
}
