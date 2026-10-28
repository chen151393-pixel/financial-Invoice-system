import { useId, useRef, useState } from "react";
import {
  Badge,
  Button,
  CardContent,
  SectionTitle,
  Stepper,
  Progress,
  Alert,
} from "../../../shared/components/ui";
import { DemoFollowup } from "./DemoFollowup";
import { DemoInvoiceReview } from "./DemoInvoiceReview";
import { followupPresets } from "./followup-presets";
import type { DemoTask } from "./workflow-data";

/** 沿用正式任务行排布；所有新增操作仅作用于当前任务的隔离演示。 */
export function DemoFollowupRow({ task }: { task: DemoTask }) {
  const [opened, setOpened] = useState(false);
  const [flowOpen, setFlowOpen] = useState(false);
  const actions = useRef<HTMLDivElement>(null);
  const panelId = useId();
  const flowId = useId();
  const preset = followupPresets[task.id];
  const action =
    task.category === "review"
      ? `核对候选发票（${task.invoices.length}）`
      : task.category === "followup"
        ? "跟进日期 / 催票"
        : "查看缺失资料";
  function closePanel() {
    setOpened(false);
    actions.current?.querySelector("button")?.focus();
  }
  return (
    <CardContent className="tb-item" role="article" aria-labelledby={`${panelId}-title`}>
      <header className="tb-item__head">
        <div className="tb-item__summary">
          <div className="tb-item__title">
            <h3 id={`${panelId}-title`}>{task.supplier}</h3>
            <Badge tone={task.tone}>{task.stage}</Badge>
          </div>
          <p className="tb-item__meta">
            <span>{task.declaration}</span>
            <span>{task.order}</span>
            <span>示例业务主体</span>
          </p>
          <p className="task-demo__row-note">{task.blocker}</p>
        </div>
        <div className="tb-item__money">
          <span>
            待收 <strong>{task.outstanding}</strong> CNY
          </span>
          <Progress
            width={preset.percent}
            text={`${preset.percent}%`}
            label={`${task.supplier} 已确认收票进度`}
            tone={preset.percent === "100" ? "success" : "info"}
          />
          <span>
            已确认 {task.received} / 应收 {task.expected}
          </span>
        </div>
        <div className="tb-item__aside" ref={actions}>
          <span className="tb-item__waiting">承诺开票 {task.promise}</span>
          <Button size="sm" aria-expanded={opened} aria-controls={panelId} onClick={() => setOpened(!opened)}>
            {opened ? "收起处理" : action}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={flowOpen}
            aria-controls={flowId}
            onClick={() => setFlowOpen(!flowOpen)}
          >
            {flowOpen ? "收起流程" : "展开流程"}
          </Button>
        </div>
      </header>
      <div className="task-demo__row-footer">
        <span>{task.timing}</span>
        <span>最近联系：{task.contact}</span>
      </div>
      {task.category === "review" && (
        <p className="task-demo__muted">候选发票待核对，尚未计入已确认收票金额。</p>
      )}
      <div id={flowId} hidden={!flowOpen}>
        {flowOpen && (
          <div className="tb-item__flow">
            <Stepper label={`${task.supplier} 任务流程`} steps={preset.steps} compact />
            <p className="tb-item__next">
              <span>下一步</span>
              {task.next}
            </p>
          </div>
        )}
      </div>
      <div id={panelId} hidden={!opened}>
        {opened && (
          <section className="task-demo__inline" aria-label={`${task.supplier} 行内处理`}>
            <SectionTitle
              title={
                task.category === "review"
                  ? "本任务的候选发票"
                  : task.category === "followup"
                    ? "本任务的跟进记录"
                    : "本任务的缺失资料"
              }
              actions={
                <Button size="sm" variant="ghost" onClick={closePanel}>
                  收起处理内容
                </Button>
              }
            />
            {task.category === "review" && <DemoInvoiceReview taskId={task.id} onBack={closePanel} />}
            {task.category === "followup" && <DemoFollowup taskId={task.id} />}
            {task.category === "documents" && (
              <Alert tone="warning" title="缺少子采购回签合同">
                {task.order}{" "}
                的发票已收齐，需补齐供应商盖章的回签合同。正式页面可复用已有批量回签上传；此示例不上传文件。
              </Alert>
            )}
          </section>
        )}
      </div>
    </CardContent>
  );
}
