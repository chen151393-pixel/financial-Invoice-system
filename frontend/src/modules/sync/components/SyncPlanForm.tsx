import { useState } from "react";
import { Button } from "../../../shared/components/Button";
import { LemonBusinessTypes } from "../LemonBusinessTypes";
import { SyncAccountScope } from "./SyncAccountScope";
import { SyncScheduleFields } from "./SyncScheduleFields";
import type { BackgroundConfig, Plan } from "../types/background";

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
        <SyncScheduleFields
          value={plan}
          saved={data.plan}
          change={(value) => setPlan({ ...plan, ...value })}
          disabled={busy}
          lookbackHint="包括执行当天，重复扫描会自动去重；更早补录或状态变化请用手动补拉。"
        />
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
