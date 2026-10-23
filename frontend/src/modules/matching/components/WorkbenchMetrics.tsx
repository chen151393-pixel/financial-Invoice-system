import { Link } from "react-router";
import { paths, reviewListPath, taskListPath } from "../../../app/paths";
import { money } from "../../../shared/format/money";
import type { Workbench, WorkbenchQuery } from "../types/workbench";
import "./workbench-metrics.css";

const NOTES: Record<Workbench["stages"][number]["key"], string> = {
  pending_review: "待财务审核或来源变化需重审",
  notify: "待保存子采购合同或待通知供应商",
  invoicing: "等待供应商开票或部分收票",
  documents: "发票已收齐，资料待补齐",
  completed: "发票收齐且资料全部到齐",
};

/** 五个业务状态分区：按报关单计数（取报关单下最慢的任务），点击进入带同样筛选条件的列表。 */
export function WorkbenchMetrics({
  stages,
  noTaskCount,
  month,
  query,
}: {
  stages: Workbench["stages"];
  noTaskCount: number;
  month: Workbench["month"];
  query: WorkbenchQuery;
}) {
  const scope = {
    account: query.account,
    supplierId: query.supplierId,
    createdFrom: query.createdFrom,
    createdTo: query.createdTo,
  };
  return (
    <div className="wb-flow" role="group" aria-label="按业务状态查看报关单">
      {stages.map((stage, index) => (
        <Link
          key={stage.key}
          className="wb-flow__card"
          to={
            stage.key === "pending_review"
              ? reviewListPath({ status: "pending", account: query.account })
              : taskListPath({ ...scope, stage: stage.key })
          }
        >
          <span className="wb-flow__step">
            <b>{index + 1}</b>
            {stage.label}
          </span>
          <span className="wb-flow__value">
            <strong>{stage.count}</strong>
            <span>张报关单</span>
          </span>
          <span className="wb-flow__note">{NOTES[stage.key]}</span>
          {stage.key === "completed" && noTaskCount > 0 && (
            <span className="wb-flow__note">另有 {noTaskCount} 张无需开票（供应商关闭通知）</span>
          )}
          <span className="wb-flow__go">
            {stage.key === "pending_review" ? "前往财务核对" : "查看开票任务"} →
          </span>
        </Link>
      ))}
      <Link className="wb-flow__card" to={paths.tasks}>
        <span className="wb-flow__step">本月任务完成</span>
        <span className="wb-flow__value">
          <strong>{month.percent === null ? "—" : `${month.percent}%`}</strong>
          <span>
            已完成 {month.completed} / {month.total} 项
          </span>
        </span>
        {month.percent !== null && (
          <span className="wb-track" role="img" aria-label={`本月新建任务完成 ${month.percent}%`}>
            <span style={{ width: `${month.percent}%` }} />
          </span>
        )}
        {month.received.map((item) => (
          <span className="wb-flow__note" key={item.currency}>
            有效已收票 {item.currency || "币种待核实"} {money(item.amount)}
          </span>
        ))}
        {month.percent === null && <span className="wb-flow__note">本月暂无新建任务</span>}
      </Link>
    </div>
  );
}
