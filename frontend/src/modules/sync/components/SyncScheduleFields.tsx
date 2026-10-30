import type { ReactNode } from "react";
import { Button } from "../../../shared/components/Button";
import { syncTime } from "../types/background";
import { SyncPhaseTag } from "./SyncPhaseTag";

export type ScheduleValue = { enabled: boolean; times: string[]; lookbackDays: number };

type Props = {
  value: ScheduleValue;
  /** 已保存的计划状态，与正在编辑的值分开展示。 */
  saved: { enabled: boolean; nextRunAt: string | null };
  change: (value: Partial<ScheduleValue>) => void;
  disabled: boolean;
  lookbackHint: ReactNode;
};

/** 每日定时计划的公共字段：启用状态、北京时间执行时点、回扫天数（柠檬云与 NS 计划共用）。校验由后端完成。 */
export function SyncScheduleFields({ value, saved, change, disabled, lookbackHint }: Props) {
  return (
    <>
      <fieldset className="sync-background__scope" disabled={disabled}>
        <legend>计划状态</legend>
        <div className="sync-background__inline">
          <label>
            <input
              type="checkbox"
              checked={value.enabled}
              onChange={(event) => change({ enabled: event.target.checked })}
            />
            启用定时同步
          </label>
          <SyncPhaseTag
            phase={saved.enabled ? "completed" : "queued"}
            label={saved.enabled ? "已启用" : "已暂停"}
          />
          <span>下次执行：{syncTime(saved.nextRunAt)}（北京时间）</span>
        </div>
      </fieldset>
      <fieldset disabled={disabled} className="sync-background__scope">
        <legend>每日执行时间</legend>
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
        <legend>扫描范围</legend>
        <label>
          每次扫描最近
          <input
            type="number"
            value={value.lookbackDays}
            onChange={(event) => change({ lookbackDays: Number(event.target.value) })}
          />
          天
        </label>
        <p>{lookbackHint}</p>
      </fieldset>
    </>
  );
}
