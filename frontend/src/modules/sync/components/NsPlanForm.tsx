import { useState } from "react";
import { Button } from "../../../shared/components/ui";
import type { NsPlan, NsPlanConfig } from "../types/ns-plan";
import { SyncScheduleFields } from "./SyncScheduleFields";

type Props = { data: NsPlanConfig; busy: boolean; save: (plan: NsPlan) => void };

/** NS 定时计划表单：单据范围 + 公共的每日时间与回扫天数；可否保存由后端 allowed/reason 与保存时校验决定。 */
export function NsPlanForm({ data, busy, save }: Props) {
  const [plan, setPlan] = useState(data.plan);
  const toggle = (kind: NsPlan["kinds"][number], checked: boolean) =>
    setPlan({
      ...plan,
      kinds: checked ? [...plan.kinds, kind] : plan.kinds.filter((value) => value !== kind),
    });
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
        <SyncScheduleFields
          value={plan}
          saved={data.plan}
          change={(value) => setPlan({ ...plan, ...value })}
          disabled={busy}
          lookbackHint="按 NS 创建日期回扫，包括执行当天；本地已有单据按 NS 身份更新、补齐，不会重复新增。更早创建的单据变化请用上方按日期拉取。"
        />
        <fieldset className="sync-background__scope" disabled={busy}>
          <legend>同步范围</legend>
          {data.kindOptions.map((option) => (
            <div key={option.value}>
              <label className="sync-background__option">
                <input
                  type="checkbox"
                  checked={plan.kinds.includes(option.value)}
                  onChange={(event) => toggle(option.value, event.target.checked)}
                />
                <span>
                  {option.label}
                  <small>{option.hint}</small>
                </span>
              </label>
            </div>
          ))}
        </fieldset>
      </div>
      <div className="sync-background__foot">
        {data.pause.allowed ? (
          <Button disabled={busy} onClick={() => save({ ...data.plan, enabled: false })}>
            暂停已保存计划
          </Button>
        ) : (
          <span />
        )}
        <Button type="submit" variant="primary" disabled={busy || (plan.enabled && !data.submit.allowed)}>
          {busy ? "正在处理…" : "保存同步计划"}
        </Button>
      </div>
    </form>
  );
}
