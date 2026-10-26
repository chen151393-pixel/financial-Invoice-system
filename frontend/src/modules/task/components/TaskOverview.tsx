import { Alert, Badge, Button, Card, Stepper, type Tone } from "../../../shared/components/ui";
import type { TaskDetail, TaskStatus } from "../types/task";
import { formatTime } from "./format";

export const sectionLabels = {
  review: "财务审核",
  documents: "开票资料",
  notification: "通知供应商",
  invoices: "等待收票",
  comparison: "比对结果",
  completion: "完成情况",
  history: "流转记录",
};
export type Section = keyof typeof sectionLabels;

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
        <div>
          <p className="itd-eyebrow">
            {task.recordNumber || "报关单号缺失"} · 审核版本 {task.reviewRevision}
          </p>
          <div className="itd-title">
            <h2>{task.supplier}</h2>
            <Badge tone={STATUS_TONE[task.status]}>{task.statusLabel}</Badge>
          </div>
          <p className="itd-subtitle">
            {task.company} · {task.orderNumbers.join("、")}
          </p>
        </div>
        <dl className="itd-amount">
          <dt>应开金额</dt>
          <dd>
            <strong>{task.expectedAmount ?? "金额待确认"}</strong> {task.currency}
          </dd>
        </dl>
      </header>

      {/* 节点 key 与内容分区一致，点击节点切换到对应分区 */}
      <Stepper
        label="任务节点，点击查看对应内容"
        steps={detail.steps}
        selectedKey={section}
        onSelect={(key) => onNavigate(key as Section)}
      />

      <Alert tone={task.status === "superseded" ? "warning" : "info"} title={task.reason}>
        <div className="itd-current">
          <span>{detail.prepare.reason}</span>
          {section !== "documents" && (
            <Button size="sm" onClick={() => onNavigate("documents")}>
              查看开票资料
            </Button>
          )}
        </div>
      </Alert>

      <dl className="itd-facts">
        <div>
          <dt>审核来源环境</dt>
          <dd>{task.account}</dd>
        </div>
        <div>
          <dt>原件下载环境</dt>
          <dd>{detail.downloadEnvironment || "未配置"}</dd>
        </div>
        <div>
          <dt>任务生成时间（北京时间）</dt>
          <dd>{formatTime(task.createdAt)}</dd>
        </div>
        <div>
          <dt>依据说明</dt>
          <dd>{detail.sourceMessage}</dd>
        </div>
      </dl>
    </Card>
  );
}
