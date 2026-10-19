import { Button } from "../../../shared/components/Button";
import type { AccountScope } from "../types/background";

type Props = {
  value: AccountScope;
  change: (value: AccountScope) => void;
  accounts: { asid: string; name: string }[] | null;
  query: () => void;
  disabled: boolean;
};
export function SyncAccountScope({ value, change, accounts, query, disabled }: Props) {
  const selection = value.accountMode === "all" ? value.excludedIds : value.accountIds;
  return (
    <fieldset className="sync-background__scope" disabled={disabled}>
      <legend>账套范围</legend>
      <div className="sync-background__inline">
        <label>
          <input
            type="radio"
            name="accountMode"
            checked={value.accountMode === "all"}
            onChange={() => change({ ...value, accountMode: "all", accountIds: [], excludedIds: [] })}
          />
          全部已授权账套
        </label>
        <label>
          <input
            type="radio"
            name="accountMode"
            checked={value.accountMode === "selected"}
            onChange={() => change({ ...value, accountMode: "selected", accountIds: [], excludedIds: [] })}
          />
          指定账套
        </label>
        <Button onClick={query}>查询授权账套</Button>
      </div>
      <p>
        {value.accountMode === "all"
          ? "每次运行前重新发现账套，新增账套自动纳入。下面勾选的账套将被排除。"
          : "勾选需要同步的账套；权限失效会记录失败，不会静默跳过。"}
      </p>
      {selection.length > 0 && (
        <p>
          已{value.accountMode === "all" ? "排除" : "选择"}：{selection.join("、")}
        </p>
      )}
      {accounts?.length === 0 && <p role="status">当前发现范围内没有授权账套。</p>}
      {accounts && accounts.length > 0 && (
        <div className="sync-background__accounts">
          {accounts.map((account) => (
            <label key={account.asid}>
              <input
                type="checkbox"
                checked={selection.includes(account.asid)}
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...selection, account.asid]
                    : selection.filter((id) => id !== account.asid);
                  change({ ...value, [value.accountMode === "all" ? "excludedIds" : "accountIds"]: next });
                }}
              />
              {account.name}
              <small>（{account.asid}）</small>
            </label>
          ))}
        </div>
      )}
      {selection.length > 0 && (
        <Button onClick={() => change({ ...value, accountIds: [], excludedIds: [] })}>清空账套勾选</Button>
      )}
    </fieldset>
  );
}
