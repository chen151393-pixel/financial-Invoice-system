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
      <h2>手动后台拉取</h2>
      <p>选择开票日期范围，提交后可离开页面。历史数据会自动按账套、日期拆批处理。</p>
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
      <div className="sync-background__inline">
        <label>
          起始开票日期
          <input
            type="date"
            value={startDate}
            onChange={(event) => setStart(event.target.value)}
            disabled={busy}
          />
        </label>
        <label>
          结束开票日期
          <input
            type="date"
            value={endDate}
            onChange={(event) => setEnd(event.target.value)}
            disabled={busy}
          />
        </label>
        <Button type="submit" variant="primary" disabled={busy || !data.submit.allowed}>
          {busy ? "正在处理…" : "提交后台拉取"}
        </Button>
      </div>
      <p>连接中断时，可按原条件再次提交查询同一任务，或进入执行记录核实；不会自动重复提交。</p>
    </form>
  );
}
