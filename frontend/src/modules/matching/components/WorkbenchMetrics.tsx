import { Link } from "react-router";
import { reviewListPath, taskListPath } from "../../../app/paths";
import type { Workbench, WorkbenchQuery } from "../types/workbench";
import "./workbench-metrics.css";

const NOTES: Record<Workbench["stages"][number]["key"], string> = {
  pending_review: "待财务审核或来源变化需重审",
  notify: "待保存子采购合同或待通知供应商",
  invoicing: "等待供应商开票或部分收票",
  documents: "发票已收齐，资料待补齐",
  completed: "发票收齐且资料全部到齐",
};

/**
 * 业务流程：五个业务状态按报关单计数（取报关单下最慢的任务），从审核到完结逐行排开，
 * 点击进入带同样筛选条件的列表。条长只按最大计数画图，不作为业务比率。
 */
export function WorkbenchMetrics({
  stages,
  noTaskCount,
  query,
}: {
  stages: Workbench["stages"];
  noTaskCount: number;
  query: WorkbenchQuery;
}) {
  const scope = {
    supplierId: query.supplierId,
    createdFrom: query.createdFrom,
    createdTo: query.createdTo,
  };
  const widest = Math.max(1, ...stages.map((stage) => stage.count));
  return (
    <section className="wb-panel" aria-labelledby="wb-flow-title">
      <div className="wb-panel__head">
        <h2 id="wb-flow-title">业务流程</h2>
        <span className="wb-count">按报关单计数</span>
      </div>
      <ol className="wb-flow" aria-label="按业务状态查看报关单">
        {stages.map((stage, index) => (
          <li key={stage.key}>
            <Link
              className="wb-flow__row"
              to={
                stage.key === "pending_review"
                  ? reviewListPath({ status: "pending" })
                  : taskListPath({ ...scope, stage: stage.key })
              }
            >
              <span className="wb-flow__step">
                <b>{index + 1}</b>
                {stage.label}
              </span>
              <span className="wb-flow__bar" aria-hidden="true">
                <span
                  data-stage={stage.key}
                  style={{ width: `${Math.max(4, Math.round((stage.count / widest) * 100))}%` }}
                />
              </span>
              <span className="wb-flow__value">
                <strong>{stage.count}</strong>
                <span>张报关单</span>
              </span>
              <span className="wb-flow__note">
                {NOTES[stage.key]}
                {stage.key === "completed" &&
                  noTaskCount > 0 &&
                  `；另有 ${noTaskCount} 张无需开票（供应商关闭通知）`}
              </span>
            </Link>
          </li>
        ))}
      </ol>
    </section>
  );
}
