import { Link } from "react-router";
import { syncBatchPath } from "../../app/paths";
import { Button } from "../../shared/components/Button";
import { Pagination } from "../../shared/components/Pagination";
import { SyncHealthGrid } from "./components/SyncHealthGrid";
import { SyncPhaseTag } from "./components/SyncPhaseTag";
import { SyncSourceCards } from "./components/SyncSourceCards";
import { useSyncBatches } from "./hooks/useSyncBatches";
import { phaseOptions, syncTime } from "./types/background";
import "./components/sync-background.css";
import "./components/sync-layout.css";

const countTags = [
  ["completed", "已完成"],
  ["partial", "部分成功"],
  ["failed", "失败"],
  ["unknown", "待核实"],
] as const;

export function SyncOverview() {
  const { data, error, loading, phase, change, refresh } = useSyncBatches();
  return (
    <>
      <SyncSourceCards plan={data?.plan ?? null} />
      <SyncHealthGrid />
      <section className="sync-background sync-background--flush" aria-label="同步执行记录">
        <div className="sync-background__head" id="sync-platforms">
          <div className="sync-background__title">
            <h2>同步执行记录</h2>
            <small>柠檬云后台批次 · 北京时间</small>
          </div>
          <div className="sync-background__inline">
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
          </div>
        </div>
        <div className="sync-background__body">
          {data && (
            <div className="sync-background__inline">
              {countTags.map(([key, label]) => (
                <SyncPhaseTag key={key} phase={key} label={`${label} ${data.counts[key] ?? 0}`} />
              ))}
            </div>
          )}
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
                      <th className="sync-background__number">读取</th>
                      <th className="sync-background__number">新增 / 更新</th>
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
                            <SyncPhaseTag phase={row.phase} label={row.label} />
                          </td>
                          <td className="sync-background__number">{row.fetched}</td>
                          <td className="sync-background__number">
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
        </div>
      </section>
    </>
  );
}
