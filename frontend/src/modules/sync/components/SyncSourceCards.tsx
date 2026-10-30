import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { syncTime } from "../types/background";

type PlanState = { enabled: boolean; nextRunAt: string | null } | null;

/** 数据同步中心的平台入口。只展示接口返回的计划状态，不在前端汇总统计。 */
export function SyncSourceCards({ plan, nsPlan }: { plan: PlanState; nsPlan: PlanState }) {
  return (
    <div className="sync-sources">
      <article className="sync-source">
        <div className="sync-source__head">
          <span className="sync-source__logo" aria-hidden="true">
            N
          </span>
          <div>
            <h2>NetSuite</h2>
            <p>采购订单 · 子采购订单 · 报关单</p>
          </div>
          {nsPlan && (
            <span className="sync-phase" data-phase={nsPlan.enabled ? "completed" : "queued"}>
              {nsPlan.enabled ? "定时计划已启用" : "定时计划已暂停"}
            </span>
          )}
        </div>
        <dl className="sync-source__facts">
          <div>
            <dt>下次执行</dt>
            <dd>{nsPlan ? syncTime(nsPlan.nextRunAt) : "—"}</dd>
          </div>
        </dl>
        <div className="sync-source__foot">
          <span>只读 NS，不修改源单据</span>
          <Link className="ui-button ui-button--primary" to={paths.syncNs}>
            进入 NS 数据同步
          </Link>
        </div>
      </article>
      <article className="sync-source">
        <div className="sync-source__head">
          <span className="sync-source__logo sync-source__logo--lemon" aria-hidden="true">
            柠
          </span>
          <div>
            <h2>柠檬云发票</h2>
            <p>全部账套后台同步 · 定时计划</p>
          </div>
          {plan && (
            <span className="sync-phase" data-phase={plan.enabled ? "completed" : "queued"}>
              {plan.enabled ? "定时计划已启用" : "定时计划已暂停"}
            </span>
          )}
        </div>
        <dl className="sync-source__facts">
          <div>
            <dt>下次执行</dt>
            <dd>{plan ? syncTime(plan.nextRunAt) : "—"}</dd>
          </div>
        </dl>
        <div className="sync-source__foot">
          <span>关闭页面后继续运行</span>
          <Link className="ui-button ui-button--primary" to={paths.syncLemon}>
            配置发票同步
          </Link>
        </div>
      </article>
    </div>
  );
}
