import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import { LemonBusinessTypes } from "../LemonBusinessTypes";
import { SyncAccountScope } from "./SyncAccountScope";
import { SyncScheduleFields } from "./SyncScheduleFields";
import type { BackgroundConfig, LemonAccountOption, Plan } from "../types/background";

type Props = {
  data: BackgroundConfig;
  accounts: LemonAccountOption[] | null;
  busy: boolean;
  query: () => void;
  save: (plan: Plan) => void;
};

/** 柠檬云定时计划表单：左栏何时执行与业务类型，右栏账套范围（含各账套版本）；校验在后端。 */
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
      <div className="sync-background__fields sync-background__fields--split">
        <div className="sync-background__column">
          <SyncScheduleFields
            value={plan}
            change={(value) => setPlan({ ...plan, ...value })}
            disabled={busy}
            dateLabel="开票日期"
            lookbackHint="包括执行当天，重复扫描会自动去重；更早补录或状态变化请在“手动补拉”页提交。"
          />
          <LemonBusinessTypes
            options={data.businessTypeOptions}
            selected={plan.businessTypes}
            onChange={(businessTypes) => setPlan({ ...plan, businessTypes })}
            disabled={busy}
          />
        </div>
        <div className="sync-background__column">
          <SyncAccountScope
            value={plan}
            change={(value) => setPlan({ ...plan, ...value })}
            accounts={accounts}
            query={query}
            disabled={busy || !data.submit.allowed}
          />
        </div>
      </div>
      <div className="sync-background__foot">
        <small>已运行的批次继续使用提交时的条件；修改计划只影响之后的执行。</small>
        <div className="sync-background__actions">
          {data.pause.allowed && (
            <Button disabled={busy} onClick={() => save({ ...data.plan, enabled: false })}>
              暂停已保存计划
            </Button>
          )}
          <Button type="submit" variant="primary" disabled={busy || !data.submit.allowed}>
            {busy ? "正在处理…" : "保存同步计划"}
          </Button>
        </div>
      </div>
    </form>
  );
}
