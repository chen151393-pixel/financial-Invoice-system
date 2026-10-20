import { Link } from "react-router";
import { paths } from "../../../app/paths";
import { Button } from "../../../shared/components/Button";
import { money } from "../../../shared/format/money";
import type { TodoKind, Workbench, WorkbenchCounts } from "../types/workbench";
import "./workbench-metrics.css";

/** 按处理环节排列的工作台卡片：点击筛选下方待办；第 4 张展示本月任务完成情况。 */
export function WorkbenchMetrics({
  counts,
  month,
  selected,
  onSelect,
}: {
  counts: WorkbenchCounts;
  month: Workbench["month"];
  selected: TodoKind;
  onSelect: (kind: TodoKind) => void;
}) {
  const cards = [
    {
      kind: "review" as const,
      label: "待财务核对",
      value: counts.review,
      unit: "张报关单",
      note: `${counts.blocked} 张缺少子采购关联`,
      warn: counts.blocked > 0,
      action: "查看核对待办",
    },
    {
      kind: "task" as const,
      label: "待开票任务",
      value: counts.task,
      unit: "项任务",
      note: `${counts.preparation} 项待备合同或通知`,
      warn: counts.preparation > 0,
      action: "查看开票待办",
    },
    {
      kind: "matching" as const,
      label: "待比对 / 复核",
      value: counts.matching,
      unit: "项发票待办",
      note: `${counts.reverify} 项已确认分配需复核`,
      warn: counts.reverify > 0,
      action: "查看比对待办",
    },
  ];
  return (
    <div className="wb-flow" role="group" aria-label="按处理环节筛选待办">
      {cards.map((card, index) => (
        <Button
          key={card.kind}
          className="wb-flow__card"
          aria-pressed={selected === card.kind}
          onClick={() => onSelect(card.kind)}
        >
          <span className="wb-flow__step">
            <b>{index + 1}</b>
            {card.label}
          </span>
          <span className="wb-flow__value">
            <strong>{card.value}</strong>
            <span>{card.unit}</span>
          </span>
          <span className={`wb-flow__note${card.warn ? " wb-flow__note--warn" : ""}`}>{card.note}</span>
          <span className="wb-flow__go">{card.action} →</span>
        </Button>
      ))}
      <Link className="wb-flow__card" to={paths.tasks}>
        <span className="wb-flow__step">
          <b>4</b>本月任务完成
        </span>
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
