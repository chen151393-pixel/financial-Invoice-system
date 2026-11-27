import { Link } from "react-router";
import { supplierTaskPath, taskPath } from "../../../app/paths";
import { Alert, Badge, Progress, Stepper } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { BoardItem } from "../types/board";
import { NODE_GLYPHS, NODE_TONES } from "./BoardNodeCards";

/**
 * 开票跟进的任务卡片：摘要与流程常驻，阻塞原因始终可见。
 * 卡片不放节点操作按钮，「跟进详情」直接进入任务当前节点处理。
 * 进入批量模式后，后端允许登记“线下已通知”的任务在节点图标左侧显示勾选框。
 */
export function BoardTaskItem({
  item,
  selection,
}: {
  item: BoardItem;
  selection?: { checked: boolean; disabled: boolean; onToggle: () => void };
}) {
  const { task } = item;
  const title = item.grouped
    ? task.supplier
    : `${task.recordNumber || "CD 号缺失"} · ${task.declarationNumber || "真实报关单号待补充"}`;
  const name = `${task.supplier} ${task.recordNumber}`;
  const detailPath = item.grouped
    ? supplierTaskPath(task.id, task.status === "completed")
    : taskPath(task.id);
  return (
    <article className="tb-item" aria-labelledby={`tb-item-${task.id}`}>
      <header className="tb-item__head">
        <div className={`tb-item__leading${selection ? " tb-item__leading--selecting" : ""}`}>
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
          <span className="tb-item__glyph" data-tone={NODE_TONES[item.currentNode]} aria-hidden="true">
            {NODE_GLYPHS[item.currentNode]}
          </span>
        </div>
        <div className="tb-item__summary">
          <div className="tb-item__title">
            <h3 id={`tb-item-${task.id}`}>
              <Link to={detailPath}>{title}</Link>
            </h3>
            <Badge tone={NODE_TONES[item.currentNode]}>{item.currentLabel}</Badge>
          </div>
          <p className="tb-item__meta">
            <span>{item.grouped ? task.recordNumber || "CD 号缺失" : task.supplier}</span>
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
            <Link
              className="ui-button ui-button--secondary ui-button--sm"
              to={detailPath}
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

      <div className="tb-item__flow">
        <Stepper label={`${task.supplier} 任务节点`} steps={item.steps} compact />
      </div>
    </article>
  );
}
