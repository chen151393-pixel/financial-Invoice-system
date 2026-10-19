import { Link } from "react-router";
import { syncBatchPath } from "../../app/paths";
import { Button } from "../../shared/components/Button";
import { Pagination } from "../../shared/components/Pagination";
import { useSyncBatches } from "./hooks/useSyncBatches";
import { phaseOptions, syncTime } from "./types/background";
import "./components/sync-background.css";

export function SyncOverview() {
  const { data, error, loading, phase, change, refresh } = useSyncBatches();
  return (
    <section className="sync-background" aria-label="同步执行记录">
      <div className="sync-background__heading" id="sync-platforms">
        <div>
          <h2>同步执行记录</h2>
          <p>柠檬云后台批次 · 每 5 秒刷新 · 北京时间</p>
        </div>
        {data && (
          <p>
            定时计划：{data.plan.enabled ? "已启用" : "已暂停"} · 下次执行：{syncTime(data.plan.nextRunAt)}
          </p>
        )}
      </div>
      <p className="sync-background__notice">
        柠檬云按账套独立执行，关闭页面后继续运行。NS 暂为手动同步，不计入此任务列表。
      </p>
      <div className="sync-background__inline sync-background__filters">
        <label>
          任务状态
          <select value={phase} onChange={(event) => change(1, event.target.value)}>
            {phaseOptions.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <Button onClick={refresh}>刷新记录</Button>
        {data && (
          <span>
            已完成 {data.counts.completed ?? 0} 批 · 部分成功 {data.counts.partial ?? 0} 批 · 失败{" "}
            {data.counts.failed ?? 0} 批 · 待核实 {data.counts.unknown ?? 0} 批
          </span>
        )}
      </div>
      {error && (
        <p role="alert" className="sync-background__error">
          {error}；已有记录可能不是最新状态。
        </p>
      )}
      {loading && !data && <p role="status">正在读取执行记录…</p>}
      {data && (
        <>
          <div className="sync-background__table" role="region" aria-label="后台同步批次表">
            <table>
              <thead>
                <tr>
                  <th>提交时间 / 触发方式</th>
                  <th>开票日期范围</th>
                  <th>状态</th>
                  <th>读取</th>
                  <th>新增 / 更新</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 ? (
                  <tr>
                    <td colSpan={6}>当前条件下没有执行记录。可进入柠檬云提交后台拉取或启用定时计划。</td>
                  </tr>
                ) : (
                  data.items.map((row) => (
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
                        <span className="sync-background__status">{row.label}</span>
                      </td>
                      <td>{row.fetched}</td>
                      <td>
                        {row.created} / {row.updated}
                      </td>
                      <td>
                        <Link to={syncBatchPath(row.requestId)}>查看账套明细</Link>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <Pagination
            label="同步任务分页"
            total={data.total}
            page={data.page}
            pageCount={data.pages}
            pageSize={data.pageSize}
            pageSizes={[20]}
            onPageChange={(page) => change(page)}
            onPageSizeChange={() => {}}
          />
        </>
      )}
    </section>
  );
}
