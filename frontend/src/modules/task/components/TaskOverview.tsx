import { Button } from "../../../shared/components/Button";
import type { TaskDetail } from "../types/task";
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
// 六个流程节点依次对应的内容分区。
const stepSections: Section[] = [
  "review",
  "documents",
  "notification",
  "invoices",
  "comparison",
  "completion",
];

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
    <section className="itd-panel" aria-label="任务概览">
      <header className="itd-heading">
        <div>
          <p className="it-help">
            {task.recordNumber || "报关单号缺失"} · 审核版本 {task.reviewRevision}
          </p>
          <h2>{task.supplier}</h2>
          <p>
            {task.company} · {task.orderNumbers.join("、")}
          </p>
        </div>
        <span className="it-status">{task.statusLabel}</span>
      </header>
      <ol className="it-steps">
        {detail.steps.map((step, index) => (
          <li
            key={step.label}
            data-state={step.state}
            aria-current={step.state === "current" ? "step" : undefined}
          >
            <button
              type="button"
              className="itd-step-link"
              aria-pressed={section === stepSections[index]}
              onClick={() => onNavigate(stepSections[index])}
            >
              <span className="itd-step-number" aria-hidden="true">
                {step.state === "done" ? "✓" : index + 1}
              </span>
              <strong>{step.label}</strong>
              <span>{step.description}</span>
            </button>
          </li>
        ))}
      </ol>
      <div className="itd-current">
        <div>
          <strong>{task.reason}</strong>
          <p>{detail.prepare.reason}</p>
        </div>
        <Button onClick={() => onNavigate("documents")}>查看开票资料</Button>
      </div>
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
          <dt>应开金额</dt>
          <dd>
            {task.expectedAmount ?? "金额待确认"} {task.currency}
          </dd>
        </div>
      </dl>
      <p className="it-help" role="status">
        {detail.sourceMessage}
      </p>
    </section>
  );
}
