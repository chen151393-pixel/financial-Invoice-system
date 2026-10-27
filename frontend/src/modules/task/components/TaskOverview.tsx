import { Alert, Badge, Card, Progress, Stepper, type Tone } from "../../../shared/components/ui";
import { money } from "../../../shared/format/money";
import type { TaskDetail, TaskStatus, TaskStepKey } from "../types/task";

// 任务详情按流程节点分区，key 与流程节点、开票跟进的节点一致
export type Section = TaskStepKey;

// 任务状态 → 徽标语义（与开票跟进列表一致）：橙=待处理，蓝=等供应商，紫=部分收票，绿=完成，灰=已替代
const STATUS_TONE: Record<TaskStatus, Tone> = {
  documents_pending: "warning",
  notify_pending: "warning",
  awaiting_invoice: "info",
  partially_received: "progress",
  documents_incomplete: "warning",
  completed: "success",
  superseded: "neutral",
};

/** 任务概览：供应商与状态、收票进度（后端金额与百分比），以及可点击切换的六个节点。 */
export function TaskOverview({
  detail,
  section,
  onNavigate,
}: {
  detail: TaskDetail;
  section: Section;
  onNavigate: (section: Section) => void;
}) {
  const task = detail.task;
  return (
    <Card className="itd-overview" aria-label="任务概览">
      <header className="itd-heading">
        <div className="itd-heading__main">
          <p className="itd-eyebrow">
            {task.recordNumber || "报关单号缺失"} · 审核版本 {task.reviewRevision}
          </p>
          <div className="itd-title">
            <h2>{task.supplier}</h2>
            <Badge tone={STATUS_TONE[task.status]}>{task.statusLabel}</Badge>
            {task.waitingLabel && <span className="itd-waiting">{task.waitingLabel}</span>}
          </div>
          <p className="itd-subtitle">
            {task.company} · {task.currency} · 子采购单 {task.orderNumbers.join("、")}
          </p>
        </div>
        <div className="itd-receipt">
          <dl>
            <div>
              <dt>应开金额</dt>
              <dd>{task.expectedAmount ? money(task.expectedAmount) : "金额待确认"}</dd>
            </div>
            <div>
              <dt>待收</dt>
              <dd>
                <strong>{task.outstandingAmount ? money(task.outstandingAmount) : "金额待确认"}</strong>{" "}
                {task.currency}
              </dd>
            </div>
          </dl>
          {task.receiptPercent && task.receiptBarPercent ? (
            <Progress
              width={task.receiptBarPercent}
              text={`已收 ${task.receiptPercent}%`}
              label="收票金额进度"
              tone={task.status === "completed" ? "success" : "info"}
            />
          ) : (
            <span className="itd-subtitle">收票进度待确认</span>
          )}
        </div>
      </header>

      {/* 节点 key 与内容分区一致，点击节点查看对应节点的处理内容 */}
      <Stepper
        label="任务节点，点击查看对应内容"
        steps={detail.steps}
        selectedKey={section}
        onSelect={(key) => onNavigate(key as Section)}
      />

      {task.status === "superseded" && (
        <Alert tone="warning" title="任务已被替代">
          {task.reason}
        </Alert>
      )}
    </Card>
  );
}
