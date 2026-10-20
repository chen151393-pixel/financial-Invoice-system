import { syncTime, type BackgroundConfig } from "../types/background";

/** 柠檬云同步状态条：授权、定时计划和下次执行时间，全部来自后端配置。 */
export function LemonSyncStatus({ data }: { data: BackgroundConfig }) {
  const plan = data.plan;
  return (
    <dl className="sync-status" aria-label="柠檬云同步状态">
      <div>
        <dt>后台同步</dt>
        <dd>
          <span className="sync-phase" data-phase={data.submit.allowed ? "completed" : "failed"}>
            {data.submit.allowed ? "可提交" : "暂不可提交"}
          </span>
        </dd>
        {!data.submit.allowed && <small>{data.submit.reason}</small>}
      </div>
      <div>
        <dt>定时计划</dt>
        <dd>
          <span className="sync-phase" data-phase={plan.enabled ? "completed" : "queued"}>
            {plan.enabled ? "已启用" : "已暂停"}
          </span>
          {plan.times.length > 0 && <span>每日 {plan.times.join("、")}</span>}
        </dd>
        <small>每次扫描最近 {plan.lookbackDays} 天</small>
      </div>
      <div>
        <dt>下次执行</dt>
        <dd>{syncTime(plan.nextRunAt)}</dd>
        <small>北京时间</small>
      </div>
    </dl>
  );
}
