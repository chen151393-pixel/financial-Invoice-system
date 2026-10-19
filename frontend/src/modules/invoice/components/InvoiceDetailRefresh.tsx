import { Button } from "../../../shared/components/Button";
import type { useDetailRefresh } from "../hooks/useDetailRefresh";
import "./invoice-detail-refresh.css";

export function InvoiceDetailRefresh({ state }: { state: ReturnType<typeof useDetailRefresh> }) {
  const { selected, busy, blocked, error, run, pending, execute, actions } = state;
  const needsQuery = Boolean(pending) || run?.status === "running";
  if (!selected.length && !busy && !error && !run && !pending) return null;
  return (
    <div className="invoice-detail-refresh" aria-busy={busy}>
      {selected.length > 0 && (
        <div className="invoice-detail-refresh__actions">
          <Button
            disabled={blocked || !selected.length || selected.some((id) => !actions[id]?.allowed)}
            onClick={() => void execute(selected)}
          >
            {busy ? "正在处理…" : "重新拉取商品明细"}
          </Button>
          <span>已选 {selected.length} 张</span>
        </div>
      )}
      {needsQuery && (
        <Button disabled={busy} onClick={() => void execute()}>
          查询补拉状态
        </Button>
      )}
      {error && (
        <p role="alert" className="invoice-list__error">
          {error}
        </p>
      )}
      {(pending || run?.status === "running") && (
        <p role="status">
          请求执行中或结果待核实，请点击“查询补拉状态”，不要重复提交。请求编号：{pending || run?.requestId}
        </p>
      )}
      {run?.status === "failed" && <p role="alert">本次未保存：{run.error}</p>}
      {run?.status === "completed" && run.result && (
        <div role="status">
          <p>
            {run.result.message} 明细完整 {run.result.completeDetails} 张，待补齐或待核实{" "}
            {run.result.pendingDetails} 张。
          </p>
          {Boolean(run.result.detailIssues?.length) && (
            <details open>
              <summary>查看未补齐原因（{run.result.detailIssueCount} 张）</summary>
              <ul>
                {run.result.detailIssues?.map((issue) => (
                  <li key={issue.number}>
                    {issue.number}：{issue.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}
