import type { AccountResult } from "../types/background";
import { SyncPhaseTag } from "./SyncPhaseTag";

/** 批次内各账套的执行结果；日期分片可展开查看失败原因与请求编号。 */
export function SyncBatchAccounts({ accounts }: { accounts: AccountResult[] }) {
  return (
    <div className="sync-background__table" role="region" aria-label="各账套执行结果">
      <table>
        <thead>
          <tr>
            <th>账套</th>
            <th>执行状态</th>
            <th>日期分片</th>
            <th className="sync-background__number">读取</th>
            <th className="sync-background__number">新增 / 更新</th>
            <th className="sync-background__number">重复 / 类型跳过</th>
            <th className="sync-background__number">明细完整 / 待补齐</th>
          </tr>
        </thead>
        <tbody>
          {accounts.map((account) => (
            <tr key={account.asid}>
              <td>
                <strong>{account.name}</strong>
                <small>{account.asid}</small>
              </td>
              <td>
                <SyncPhaseTag phase={account.phase} label={account.label} />
              </td>
              <td>
                <details>
                  <summary>
                    完成 {account.completed} / {account.total}
                  </summary>
                  <ul className="sync-background__windows">
                    {account.windows.map((part) => (
                      <li key={part.requestId}>
                        {part.startDate} 至 {part.endDate} · {part.label}
                        {part.error && <p className="sync-background__error">{part.error}</p>}
                        <small>请求：{part.requestId}</small>
                      </li>
                    ))}
                  </ul>
                </details>
              </td>
              <td className="sync-background__number">{account.counts.fetched}</td>
              <td className="sync-background__number">
                {account.counts.created} / {account.counts.updated}
              </td>
              <td className="sync-background__number">
                {account.counts.unchanged} / {account.counts.excluded}
              </td>
              <td className="sync-background__number">
                {account.counts.completeDetails} / {account.counts.pendingDetails}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
