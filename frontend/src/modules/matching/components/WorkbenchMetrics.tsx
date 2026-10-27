import { Link } from "react-router";
import { reviewListPath, taskListPath } from "../../../app/paths";
import type { Workbench, WorkbenchQuery } from "../types/workbench";
import "./workbench-metrics.css";

// 漏斗每一步“卡在上一步”的报关单即对应的业务状态分区
const STUCK: Record<string, Workbench["stages"][number]["key"]> = {
  approved: "pending_review",
  notified: "notify",
  received: "invoicing",
  completed: "documents",
};

/**
 * 业务流程漏斗：后端由五个业务状态累加出“至少走到这一步”的报关单数与上一环节通过率；
 * 每步附“卡在上一环节”的分区计数，点击进入带同样筛选条件的列表。条长只按第一步计数画图。
 */
export function WorkbenchMetrics({
  stages,
  funnel,
  noTaskCount,
  query,
}: {
  stages: Workbench["stages"];
  funnel: Workbench["funnel"];
  noTaskCount: number;
  query: WorkbenchQuery;
}) {
  const scope = {
    supplierId: query.supplierId,
    createdFrom: query.createdFrom,
    createdTo: query.createdTo,
  };
  const first = Math.max(1, funnel[0]?.count ?? 0);
  const stageOf = (key: string) => stages.find((stage) => stage.key === key);
  return (
    <section className="wb-panel" aria-labelledby="wb-flow-title">
      <div className="wb-panel__head">
        <h2 id="wb-flow-title">业务流程</h2>
        <span className="wb-count">按报关单累计</span>
      </div>
      <ol className="wb-flow" aria-label="业务流程漏斗">
        {funnel.map((step, index) => {
          const stuck = STUCK[step.key] ? stageOf(STUCK[step.key]) : undefined;
          return (
            <li key={step.key} className="wb-flow__row">
              <span className="wb-flow__step">
                <b>{index + 1}</b>
                {step.label}
              </span>
              <span className="wb-flow__bar" aria-hidden="true">
                <span
                  data-step={index}
                  style={{ width: `${Math.max(4, Math.round((step.count / first) * 100))}%` }}
                />
              </span>
              <span className="wb-flow__value">
                <strong>{step.count}</strong>
                <span>张报关单</span>
              </span>
              <span className="wb-flow__note">
                {step.rate === null ? "起点" : `上一环节通过 ${step.rate}%`}
                {stuck && stuck.count > 0 && (
                  <>
                    {" · "}
                    <Link
                      to={
                        stuck.key === "pending_review"
                          ? reviewListPath({ status: "pending" })
                          : taskListPath({ ...scope, stage: stuck.key })
                      }
                    >
                      {stuck.count} 张{stuck.label} →
                    </Link>
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ol>
      {noTaskCount > 0 && (
        <p className="wb-report-note wb-flow__foot">
          另有 {noTaskCount} 张无需开票（供应商关闭通知），不计入漏斗。
        </p>
      )}
    </section>
  );
}
