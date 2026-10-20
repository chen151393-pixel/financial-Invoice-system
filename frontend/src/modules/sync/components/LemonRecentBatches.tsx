import { Link } from "react-router";
import { paths, syncBatchPath } from "../../../app/paths";
import { useSyncBatches } from "../hooks/useSyncBatches";
import { syncTime } from "../types/background";
import { SyncPhaseTag } from "./SyncPhaseTag";

/** 柠檬云页面的最近执行：展示执行记录第一页的前三条，完整记录在数据同步中心。 */
export function LemonRecentBatches() {
  const { data, error, loading } = useSyncBatches();
  const rows = data?.items.slice(0, 3) ?? [];
  return (
    <section className="sync-background sync-background--flush" aria-label="最近执行">
      <div className="sync-background__head">
        <h2>最近执行</h2>
        <Link to={paths.sync}>全部执行记录 →</Link>
      </div>
      <div className="sync-background__body">
        {error && (
          <p role="alert" className="sync-background__error">
            {error}
          </p>
        )}
        {loading && !data && <p role="status">正在读取执行记录…</p>}
        {data && rows.length === 0 && <p>还没有执行记录。</p>}
        {rows.length > 0 && (
          <div className="sync-background__table" role="region" aria-label="最近执行的后台批次">
            <table>
              <thead>
                <tr>
                  <th>提交时间 / 触发方式</th>
                  <th>开票日期范围</th>
                  <th>状态</th>
                  <th className="sync-background__number">读取</th>
                  <th className="sync-background__number">新增 / 更新</th>
                  <th className="sync-background__number">失败</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.requestId}>
                    <td>
                      {syncTime(row.createdAt)}
                      <small>{row.trigger === "schedule" ? "定时计划" : "手动提交"}</small>
                    </td>
                    <td>
                      {row.startDate} 至 {row.endDate}
                      <small>{row.businessTypes.join("、")}</small>
                    </td>
                    <td>
                      <SyncPhaseTag phase={row.phase} label={row.label} />
                    </td>
                    <td className="sync-background__number">{row.fetched}</td>
                    <td className="sync-background__number">
                      {row.created} / {row.updated}
                    </td>
                    <td className="sync-background__number">{row.failed}</td>
                    <td>
                      <Link to={syncBatchPath(row.requestId)}>查看账套明细</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
