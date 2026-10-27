import { useId, useState } from "react";
import { Link } from "react-router";
import { taskPath } from "../../../app/paths";
import { Alert, Badge, Button, CardContent, Progress, Stepper } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { BoardItem, BoardNodeKey } from "../types/board";
import { NODE_TONES } from "./BoardNodeTabs";

// 按当前节点直达详情页对应分区（详情页按 #task-分区 定位）；采购需亲自处理的节点用主按钮
const SHORTCUTS: Partial<Record<BoardNodeKey, { section: string; label: string; primary?: boolean }>> = {
  documents: { section: "documents", label: "查看合同" },
  notification: { section: "notification", label: "去通知供应商", primary: true },
  invoices: { section: "invoices", label: "查看收票" },
  comparison: { section: "comparison", label: "查看比对" },
  completion: { section: "documents", label: "补齐资料", primary: true },
};

/** 合并面板内的任务行：流程默认展开，可按需收起；阻塞原因始终可见。 */
export function BoardTaskItem({ item }: { item: BoardItem }) {
  const [expanded, setExpanded] = useState(true);
  const flowId = useId();
  const { task } = item;
  const orders = task.orderNumbers.join("、");
  const shortcut = SHORTCUTS[item.currentNode];
  return (
    <CardContent className="tb-item" role="article" aria-labelledby={`tb-item-${task.id}`}>
      <header className="tb-item__head">
        <div className="tb-item__summary">
          <div className="tb-item__title">
            <h3 id={`tb-item-${task.id}`}>{task.supplier}</h3>
            <Badge tone={NODE_TONES[item.currentNode]}>{item.currentLabel}</Badge>
          </div>
          <p className="tb-item__meta">
            <span>{task.recordNumber || "报关单号缺失"}</span>
            <span title={orders}>{orders || "子采购单号缺失"}</span>
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
              text={`${task.receiptPercent}%`}
              label="收票金额进度"
              tone={item.currentNode === "done" ? "success" : "info"}
            />
          ) : (
            <span>收票进度待确认</span>
          )}
        </div>
        <div className="tb-item__aside">
          <span className="tb-item__waiting">{task.waitingLabel || "等待情况待获取"}</span>
          {shortcut && (
            <Link
              className={`ui-button ${shortcut.primary ? "ui-button--primary" : "ui-button--secondary"}`}
              to={`${taskPath(task.id)}#task-${shortcut.section}`}
              aria-label={`${task.supplier} ${task.recordNumber} ${shortcut.label}`}
            >
              {shortcut.label}
            </Link>
          )}
          <Link
            className="ui-button ui-button--secondary"
            to={taskPath(task.id)}
            aria-label={`${task.supplier} ${task.recordNumber} 跟进详情`}
          >
            跟进详情
          </Link>
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={expanded}
            aria-controls={flowId}
            aria-label={`${task.supplier} ${task.recordNumber} ${expanded ? "收起流程" : "展开流程"}`}
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? "收起流程" : "展开流程"}
          </Button>
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
            <p className="tb-item__next">
              <span>下一步</span>
              {item.nextAction}
            </p>
          </div>
        )}
      </div>
    </CardContent>
  );
}
