import { useState } from "react";
import { Button } from "../../../shared/components/ui";
import type { NsPlan, NsPlanConfig } from "../types/ns-plan";
import { SyncScheduleFields } from "./SyncScheduleFields";

type Props = { data: NsPlanConfig; busy: boolean; save: (plan: NsPlan) => void };

/**
 * NS 定时计划表单：左栏何时执行（公共字段），右栏同步范围；底部为保存规则、自动暂停原因与操作。
 * 可否保存由后端 allowed/reason 与保存时校验决定。
 */
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
      <div className="sync-background__fields sync-background__fields--split">
        <div className="sync-background__column">
          <SyncScheduleFields
            value={plan}
            change={(value) => setPlan({ ...plan, ...value })}
            disabled={busy}
            dateLabel="创建日期"
            lookbackHint="包括执行当天；更早创建的单据变化请在“手动补拉”页按日期拉取。"
          />
        </div>
        <div className="sync-background__column">
          <fieldset className="sync-background__scope" disabled={busy}>
            <legend>同步范围</legend>
            <div className="sync-background__choices">
              {data.kindOptions.map((option) => (
                <label key={option.value} className="sync-background__option">
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
              ))}
            </div>
          </fieldset>
          <details className="sync-background__rules">
            <summary>保存规则</summary>
            <p>{data.coverage}</p>
          </details>
        </div>
      </div>
      <div className="sync-background__foot">
        {data.plan.pausedReason ? (
          <p role="status" className="sync-background__paused">
            {data.plan.pausedReason}
          </p>
        ) : (
          <small>本地已有单据按 NS 身份更新、补齐，没有的新增；不写入 NS。</small>
        )}
        <div className="sync-background__actions">
          {data.pause.allowed && (
            <Button disabled={busy} onClick={() => save({ ...data.plan, enabled: false })}>
              暂停已保存计划
            </Button>
          )}
          <Button type="submit" variant="primary" disabled={busy || (plan.enabled && !data.submit.allowed)}>
            {busy ? "正在处理…" : "保存同步计划"}
          </Button>
        </div>
      </div>
    </form>
  );
}
