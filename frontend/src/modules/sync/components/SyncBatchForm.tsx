import { useRef, useState } from "react";
import { Button } from "../../../shared/components/Button";
import { LemonBusinessTypes } from "../LemonBusinessTypes";
import { SyncAccountScope } from "./SyncAccountScope";
import type { AccountScope, BackgroundConfig, BatchInput } from "../types/background";

type Props = {
  data: BackgroundConfig;
  accounts: { asid: string; name: string }[] | null;
  busy: boolean;
  query: () => void;
  submit: (body: BatchInput) => void;
};
export function SyncBatchForm({ data, accounts, busy, query, submit }: Props) {
  const [scope, setScope] = useState<AccountScope>({
    accountMode: data.plan.accountMode,
    accountIds: data.plan.accountIds,
    excludedIds: data.plan.excludedIds,
    businessTypes: data.plan.businessTypes,
  });
  const [startDate, setStart] = useState("");
  const [endDate, setEnd] = useState("");
  const pending = useRef<{ signature: string; requestId: string } | null>(null);
  return (
    <form
      className="sync-background__form"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        const signature = JSON.stringify({ ...scope, startDate, endDate });
        if (pending.current?.signature !== signature)
          pending.current = { signature, requestId: crypto.randomUUID() };
        submit({ ...scope, startDate, endDate, requestId: pending.current.requestId });
      }}
    >
      <div className="sync-background__fields">
        <SyncAccountScope
          value={scope}
          change={setScope}
          accounts={accounts}
          query={query}
          disabled={busy || !data.submit.allowed}
        />
        <LemonBusinessTypes
          options={data.businessTypeOptions}
          selected={scope.businessTypes}
          onChange={(businessTypes) => setScope({ ...scope, businessTypes })}
          disabled={busy}
        />
        <fieldset className="sync-background__scope" disabled={busy}>
          <legend>开票日期</legend>
          <div className="sync-background__inline">
            <label>
              起始开票日期
              <input type="date" value={startDate} onChange={(event) => setStart(event.target.value)} />
            </label>
            <label>
              结束开票日期
              <input type="date" value={endDate} onChange={(event) => setEnd(event.target.value)} />
            </label>
          </div>
        </fieldset>
      </div>
      <div className="sync-background__foot">
        <small>连接中断时可按原条件再次提交查询同一任务，不会重复执行。</small>
        <Button type="submit" variant="primary" disabled={busy || !data.submit.allowed}>
          {busy ? "正在处理…" : "提交后台拉取"}
        </Button>
      </div>
    </form>
  );
}
