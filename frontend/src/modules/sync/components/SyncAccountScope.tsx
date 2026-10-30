import { Button } from "../../../shared/components/Button";
import { Badge } from "../../../shared/components/ui";
import type { AccountScope, LemonAccountOption } from "../types/background";

type Props = {
  value: AccountScope;
  change: (value: AccountScope) => void;
  accounts: LemonAccountOption[] | null;
  query: () => void;
  disabled: boolean;
};

/**
 * 账套范围（手动拉取与定时计划共用）：全部或指定账套；查询后列出各账套版本与能拉到的内容。
 * 版本与内容说明由后端给出：专业版含商品明细，免费版只有票头。
 */
export function SyncAccountScope({ value, change, accounts, query, disabled }: Props) {
  const excluding = value.accountMode === "all";
  const selection = excluding ? value.excludedIds : value.accountIds;
  return (
    <fieldset className="sync-background__scope" disabled={disabled}>
      <legend>账套范围</legend>
      <div className="sync-background__inline">
        <label>
          <input
            type="radio"
            name="accountMode"
            checked={excluding}
            onChange={() => change({ ...value, accountMode: "all", accountIds: [], excludedIds: [] })}
          />
          全部已授权账套
        </label>
        <label>
          <input
            type="radio"
            name="accountMode"
            checked={!excluding}
            onChange={() => change({ ...value, accountMode: "selected", accountIds: [], excludedIds: [] })}
          />
          指定账套
        </label>
        <Button onClick={query}>查询授权账套</Button>
      </div>
      <p>
        {excluding
          ? "每次运行前重新发现账套，新增账套自动纳入。下面勾选的账套将被排除。"
          : "勾选需要同步的账套；权限失效会记录失败，不会静默跳过。"}
      </p>
      {selection.length > 0 && (
        <p>
          已{excluding ? "排除" : "选择"}：{selection.join("、")}
        </p>
      )}
      {!accounts && <p>查询授权账套后显示各账套的版本与可拉取内容。</p>}
      {accounts?.length === 0 && <p role="status">当前发现范围内没有授权账套。</p>}
      {accounts && accounts.length > 0 && (
        <div className="sync-background__accounts" role="region" aria-label="授权账套">
          <table>
            <thead>
              <tr>
                <th>{excluding ? "排除" : "选择"}</th>
                <th>账套</th>
                <th>版本</th>
                <th>拉取内容</th>
              </tr>
            </thead>
            <tbody>
              {accounts.map((account) => (
                <tr key={account.asid}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`${excluding ? "排除" : "选择"} ${account.name}`}
                      checked={selection.includes(account.asid)}
                      onChange={(event) => {
                        const next = event.target.checked
                          ? [...selection, account.asid]
                          : selection.filter((id) => id !== account.asid);
                        change({ ...value, [excluding ? "excludedIds" : "accountIds"]: next });
                      }}
                    />
                  </td>
                  <td>
                    {account.name}
                    <small>{account.asid}</small>
                  </td>
                  <td>
                    <Badge tone={account.edition === "professional" ? "info" : "neutral"} dot={false}>
                      {account.editionLabel}
                    </Badge>
                  </td>
                  <td>{account.content}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {selection.length > 0 && (
        <Button onClick={() => change({ ...value, accountIds: [], excludedIds: [] })}>清空账套勾选</Button>
      )}
    </fieldset>
  );
}
