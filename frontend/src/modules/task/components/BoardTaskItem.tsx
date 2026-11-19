import { useId, useState } from "react";
import { Link } from "react-router";
import { taskPath } from "../../../app/paths";
import { Alert, Badge, Button, Progress, Stepper } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { BoardItem } from "../types/board";
import { NODE_GLYPHS, NODE_TONES } from "./BoardNodeCards";

/**
 * 开票跟进的任务卡片：摘要常驻，流程默认展开、可收起；阻塞原因始终可见。
 * 卡片不放节点操作按钮，「跟进详情」直接进入任务当前节点处理。
 * 后端允许批量登记“线下已通知”的任务在标题前显示勾选框；能否登记不在前端判断。
 */
export function BoardTaskItem({
  item,
  selection,
}: {
  item: BoardItem;
  selection?: { checked: boolean; disabled: boolean; onToggle: () => void };
}) {
  const [expanded, setExpanded] = useState(true);
  const flowId = useId();
  const { task } = item;
  const orders = task.orderNumbers.join("、");
  const name = `${task.supplier} ${task.recordNumber}`;
  return (
    <article className="tb-item" aria-labelledby={`tb-item-${task.id}`}>
      <header className="tb-item__head">
        <span className="tb-item__glyph" data-tone={NODE_TONES[item.currentNode]} aria-hidden="true">
          {NODE_GLYPHS[item.currentNode]}
        </span>
        <div className="tb-item__summary">
          <div className="tb-item__title">
            {selection && item.notifyRecord.allowed && (
              <input
                type="checkbox"
                className="tb-item__check"
                checked={selection.checked}
                disabled={selection.disabled}
                aria-label={`选择 ${name}，用于批量登记已通知`}
                onChange={selection.onToggle}
              />
            )}
            <h3 id={`tb-item-${task.id}`}>
              <Link to={taskPath(task.id)}>{task.supplier}</Link>
            </h3>
            <Badge tone={NODE_TONES[item.currentNode]}>{item.currentLabel}</Badge>
          </div>
          <p className="tb-item__meta">
            <span>{task.recordNumber || "报关单号缺失"}</span>
            <span title={orders}>子采购 {orders || "单号缺失"}</span>
            <span>{task.company}</span>
          </p>
        </div>
        <div className="tb-item__money">
          <span>
            待收 <strong>{task.outstandingAmount ? money(task.outstandingAmount) : "金额待确认"}</strong>{" "}
            {task.currency || "币种待确认"}
          </span>
          {task.receiptPercent && task.receiptBarPercent ? (
            <Progress
              width={task.receiptBarPercent}
              text={`已收 ${task.receiptPercent}%`}
              label="收票金额进度"
              tone={item.currentNode === "done" ? "success" : "info"}
            />
          ) : (
            <span>收票进度待确认</span>
          )}
        </div>
        <div className="tb-item__aside">
          <span className="tb-item__waiting">{task.waitingLabel || "等待情况待获取"}</span>
          <div className="tb-item__actions">
            <Button
              variant="ghost"
              size="sm"
              aria-expanded={expanded}
              aria-controls={flowId}
              aria-label={`${name} ${expanded ? "收起流程" : "展开流程"}`}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "收起流程" : "展开流程"}
            </Button>
            <Link
              className="ui-button ui-button--secondary ui-button--sm"
              to={taskPath(task.id)}
              aria-label={`${name} 跟进详情`}
            >
              跟进详情
            </Link>
          </div>
        </div>
      </header>

      {item.blockedReason && (
        <Alert tone="danger" title="暂不能推进">
          {item.blockedReason}
        </Alert>
      )}

      <div id={flowId} hidden={!expanded}>
        {expanded && (
          <div className="tb-item__flow">
            <Stepper label={`${task.supplier} 任务节点`} steps={item.steps} compact />
          </div>
        )}
      </div>
    </article>
  );
}
