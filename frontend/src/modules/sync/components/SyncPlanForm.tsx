import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import { LemonBusinessTypes } from "../LemonBusinessTypes";
import { SyncAccountScope } from "./SyncAccountScope";
import { SyncPhaseTag } from "./SyncPhaseTag";
import { syncTime, type BackgroundConfig, type Plan } from "../types/background";

type Props = {
  data: BackgroundConfig;
  accounts: { asid: string; name: string }[] | null;
  busy: boolean;
  query: () => void;
  save: (plan: Plan) => void;
};
export function SyncPlanForm({ data, accounts, busy, query, save }: Props) {
  const [plan, setPlan] = useState(data.plan);
  return (
    <form
      className="sync-background__form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        save(plan);
      }}
    >
      <div className="sync-background__fields">
        <fieldset className="sync-background__scope" disabled={busy}>
          <legend>计划状态</legend>
          <div className="sync-background__inline">
            <label>
              <input
                type="checkbox"
                checked={plan.enabled}
                onChange={(event) => setPlan({ ...plan, enabled: event.target.checked })}
              />
              启用定时同步
            </label>
            <SyncPhaseTag
              phase={data.plan.enabled ? "completed" : "queued"}
              label={data.plan.enabled ? "已启用" : "已暂停"}
            />
            <span>下次执行：{syncTime(data.plan.nextRunAt)}（北京时间）</span>
          </div>
        </fieldset>
        <fieldset disabled={busy} className="sync-background__scope">
          <legend>每日执行时间</legend>
          <div className="sync-background__inline">
            {plan.times.map((value, index) => (
              <span className="sync-time" key={index}>
                <input
                  aria-label={`执行时间 ${index + 1}`}
                  type="time"
                  value={value}
                  onChange={(event) =>
                    setPlan({
                      ...plan,
                      times: plan.times.map((time, i) => (i === index ? event.target.value : time)),
                    })
                  }
                />
                <button
                  type="button"
                  aria-label={`移除执行时间 ${value}`}
                  onClick={() => setPlan({ ...plan, times: plan.times.filter((_, i) => i !== index) })}
                >
                  ×
                </button>
              </span>
            ))}
            <Button onClick={() => setPlan({ ...plan, times: [...plan.times, "14:00"] })}>
              ＋ 添加执行时间
            </Button>
          </div>
        </fieldset>
        <fieldset disabled={busy} className="sync-background__scope">
          <legend>扫描范围</legend>
          <label>
            每次扫描最近
            <input
              type="number"
              value={plan.lookbackDays}
              onChange={(event) => setPlan({ ...plan, lookbackDays: Number(event.target.value) })}
            />
            天
          </label>
          <p>包括执行当天，重复扫描会自动去重；更早补录或状态变化请用手动补拉。</p>
        </fieldset>
        <SyncAccountScope
          value={plan}
          change={(value) => setPlan({ ...plan, ...value })}
          accounts={accounts}
          query={query}
          disabled={busy || !data.submit.allowed}
        />
        <LemonBusinessTypes
          options={data.businessTypeOptions}
          selected={plan.businessTypes}
          onChange={(businessTypes) => setPlan({ ...plan, businessTypes })}
          disabled={busy}
        />
      </div>
      <div className="sync-background__foot">
        {data.pause.allowed ? (
          <Button disabled={busy} onClick={() => save({ ...data.plan, enabled: false })}>
            暂停已保存计划
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" variant="primary" disabled={busy || !data.submit.allowed}>
          {busy ? "正在处理…" : "保存同步计划"}
        </Button>
      </div>
    </form>
  );
}
