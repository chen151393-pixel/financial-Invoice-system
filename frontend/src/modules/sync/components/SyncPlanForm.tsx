import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import { LemonBusinessTypes } from "../LemonBusinessTypes";
import { SyncAccountScope } from "./SyncAccountScope";
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
      <div className="sync-background__heading">
        <div>
          <h2>定时同步计划</h2>
          <p>北京时间 · 下次执行：{syncTime(data.plan.nextRunAt)}</p>
        </div>
        <span className="sync-background__status">{data.plan.enabled ? "已启用" : "已暂停"}</span>
      </div>
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
      <fieldset disabled={busy} className="sync-background__schedule">
        <legend>每日执行时间</legend>
        {plan.times.map((value, index) => (
          <div className="sync-background__inline" key={index}>
            <label>
              时间 {index + 1}
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
            </label>
            <Button onClick={() => setPlan({ ...plan, times: plan.times.filter((_, i) => i !== index) })}>
              移除此时间
            </Button>
          </div>
        ))}
        <Button onClick={() => setPlan({ ...plan, times: [...plan.times, "14:00"] })}>添加执行时间</Button>
      </fieldset>
      <div className="sync-background__inline">
        <label>
          每次扫描最近天数
          <input
            type="number"
            value={plan.lookbackDays}
            onChange={(event) => setPlan({ ...plan, lookbackDays: Number(event.target.value) })}
            disabled={busy}
          />
        </label>
        <label>
          <input
            type="checkbox"
            checked={plan.enabled}
            onChange={(event) => setPlan({ ...plan, enabled: event.target.checked })}
            disabled={busy}
          />
          启用定时同步
        </label>
      </div>
      <p>包括执行当天，重复扫描会自动去重。更早补录或状态变化，请用手动历史补拉覆盖对应日期。</p>
      <Button type="submit" variant="primary" disabled={busy || !data.submit.allowed}>
        {busy ? "正在处理…" : "保存同步计划"}
      </Button>
      {data.pause.allowed && (
        <Button disabled={busy} onClick={() => save({ ...data.plan, enabled: false })}>
          暂停已保存计划
        </Button>
      )}
    </form>
  );
}
