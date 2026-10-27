import { Link } from "react-router";
import { reviewListPath, taskListPath } from "../../../app/paths";
import type { Workbench } from "../types/workbench";
import "./workbench-metrics.css";

/**
 * 业务流程漏斗：后端按报关单给出六步"至少走到这一步"的计数、上一环节通过率、整体完结率，
 * 以及卡在上一步的分项（待财务审核或开票跟进节点），分项链接进入对应列表。条长只按第一步计数画图。
 */
export function WorkbenchMetrics({
  funnel,
  noTaskCount,
}: {
  funnel: NonNullable<Workbench["funnel"]>;
  noTaskCount: number;
}) {
  const first = Math.max(1, funnel.steps[0]?.count ?? 0);
  return (
    <section className="wb-panel" aria-labelledby="wb-flow-title">
      <div className="wb-panel__head wb-panel__head--split">
        <div>
          <h2 id="wb-flow-title">业务流程漏斗</h2>
          <p className="wb-panel__sub">报关单从入库到资料齐全完结，各环节通过量与停留量</p>
        </div>
        <span className="wb-flow__rate">
          整体完结率 <strong>{funnel.completionRate === null ? "—" : `${funnel.completionRate}%`}</strong>
        </span>
      </div>
      <ol className="wb-flow" aria-label="业务流程漏斗">
        {funnel.steps.map((step, index) => (
          <li key={step.key} className="wb-flow__row">
            <span className="wb-flow__step">{step.label}</span>
            <span className="wb-flow__bar">
              <span
                data-step={index}
                style={{ width: `${Math.max(6, Math.round((step.count / first) * 100))}%` }}
              >
                {step.count}
              </span>
            </span>
            <span className="wb-flow__note">
              <span>
                {index === 0
                  ? "起点"
                  : step.rate === null
                    ? "上一环节为 0，暂无通过率"
                    : `上一环节通过 ${step.rate}%`}
              </span>
              {step.stuck.map((item) => (
                <Link
                  key={item.key}
                  className="wb-flow__stuck"
                  to={
                    item.key === "pending_review"
                      ? reviewListPath({ status: "pending" })
                      : taskListPath({ node: item.key })
                  }
                >
                  {item.count} 张{item.label} →
                </Link>
              ))}
            </span>
          </li>
        ))}
      </ol>
      {noTaskCount > 0 && (
        <p className="wb-report-note">另有 {noTaskCount} 张无需开票（供应商关闭通知），不计入漏斗。</p>
      )}
    </section>
  );
}
