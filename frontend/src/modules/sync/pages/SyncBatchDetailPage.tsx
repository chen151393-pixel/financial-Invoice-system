import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { paths, syncBatchPath } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { Pagination } from "../../../shared/components/Pagination";
import { useSyncBatchDetail } from "../hooks/useSyncBatchDetail";
import { syncTime } from "../types/background";
import "../components/sync-background.css";

export function SyncBatchDetailPage() {
  const { requestId = "" } = useParams();
  const [query, setQuery] = useSearchParams();
  const { data, error, busy, refresh, retry } = useSyncBatchDetail(
    requestId,
    Number(query.get("page") || "1"),
  );
  const navigate = useNavigate();
  return (
    <section className="sync-background" aria-label="后台任务详情">
      <div className="sync-background__heading">
        <Link to={paths.sync}>返回执行记录</Link>
        <Button onClick={refresh}>刷新任务状态</Button>
      </div>
      {error && (
        <p role="alert" className="sync-background__error">
          {error}
        </p>
      )}
      {!data && !error && <p role="status">正在读取任务详情…</p>}
      {data && (
        <>
          <div className="sync-background__heading">
            <div>
              <h2>{data.label}</h2>
              <p>{data.message}</p>
            </div>
            <Button
              disabled={busy || !data.retry.allowed}
              onClick={() => void retry((id) => navigate(syncBatchPath(id)))}
            >
              {busy ? "正在提交…" : "重试失败分片"}
            </Button>
          </div>
          <p>{data.retry.reason}</p>
          <dl className="sync-background__facts">
            <div>
              <dt>开票日期范围</dt>
              <dd>
                {data.startDate} 至 {data.endDate}
              </dd>
            </div>
            <div>
              <dt>业务类型</dt>
              <dd>{data.businessTypes.join("、")}</dd>
            </div>
            <div>
              <dt>提交时间</dt>
              <dd>{syncTime(data.createdAt)}</dd>
            </div>
            <div>
              <dt>结束时间</dt>
              <dd>{syncTime(data.finishedAt)}</dd>
            </div>
          </dl>
          {data.phase === "unknown" && (
            <p role="alert" className="sync-background__error">
              部分提交结果无法确认，已保留原请求。请管理员核实进程与数据库提交状态，不能直接重发或清除运行记录。
            </p>
          )}
          {data.accounts.length === 0 && (
            <p role="status">
              {data.poll
                ? "正在等待后台发现账套，稍后自动更新。"
                : "本批次没有生成账套任务，请查看上方原因。"}
            </p>
          )}
          {data.accounts.length > 0 && (
            <div className="sync-background__table" role="region" aria-label="各账套执行结果">
              <table>
                <thead>
                  <tr>
                    <th>账套 / 日期分片</th>
                    <th>执行状态</th>
                    <th>读取</th>
                    <th>新增 / 更新</th>
                    <th>重复 / 类型跳过</th>
                    <th>明细完整 / 待补齐</th>
                  </tr>
                </thead>
                <tbody>
                  {data.accounts.map((account) => (
                    <tr key={account.asid}>
                      <td>
                        <strong>{account.name}</strong>
                        <small>{account.asid}</small>
                        <details>
                          <summary>
                            日期分片（完成 {account.completed} / {account.total}）
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
                      <td>{account.label}</td>
                      <td>{account.counts.fetched}</td>
                      <td>
                        {account.counts.created} / {account.counts.updated}
                      </td>
                      <td>
                        {account.counts.unchanged} / {account.counts.excluded}
                      </td>
                      <td>
                        {account.counts.completeDetails} / {account.counts.pendingDetails}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {data.total > 0 && (
            <Pagination
              label="账套结果分页"
              total={data.total}
              page={data.page}
              pageCount={data.pages}
              pageSize={data.pageSize}
              pageSizes={[20]}
              onPageChange={(page) => setQuery({ page: String(page) })}
              onPageSizeChange={() => {}}
            />
          )}
          <p className="sync-background__notice">
            已完成表示日期范围扫描和保存已提交；无新增属于正常结果，明细待补齐会单独列出。统计按各次分片读取计数。
          </p>
          <p className="sync-background__request">批次编号：{data.requestId}</p>
          <Link to={paths.invoices}>查看发票台账</Link>
        </>
      )}
    </section>
  );
}
