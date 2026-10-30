import { syncTime } from "../types/background";
import type { NsPlanConfig } from "../types/ns-plan";

/** NS 同步状态条（与柠檬云 `LemonSyncStatus` 同样三格）：能否启用、定时计划与下次执行，全部来自后端配置。 */
export function NsSyncStatus({ data }: { data: NsPlanConfig }) {
  const plan = data.plan;
  return (
    <dl className="sync-status" aria-label="NS 同步状态">
      <div>
        <dt>定时同步</dt>
        <dd>
          <span className="sync-phase" data-phase={data.submit.allowed ? "completed" : "failed"}>
            {data.submit.allowed ? "可启用" : "暂不可启用"}
          </span>
        </dd>
        <small>{data.submit.allowed ? "只读 NS 正式环境，不写入 NS" : data.submit.reason}</small>
      </div>
      <div>
        <dt>定时计划</dt>
        <dd>
          <span className="sync-phase" data-phase={plan.enabled ? "completed" : "queued"}>
            {plan.enabled ? "已启用" : "已暂停"}
          </span>
          {plan.times.length > 0 && <span>每日 {plan.times.join("、")}</span>}
        </dd>
        <small>
          {plan.pausedReason ? "已自动暂停，原因见定时计划" : `每次扫描最近 ${plan.lookbackDays} 天`}
        </small>
      </div>
      <div>
        <dt>下次执行</dt>
        <dd>{syncTime(plan.nextRunAt)}</dd>
        <small>北京时间</small>
      </div>
    </dl>
  );
}
