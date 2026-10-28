import { useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  Field,
  FilterBar,
} from "../../../shared/components/ui";
import { demoTasks } from "./workflow-data";

export function DemoFollowup({ taskId }: { taskId?: string }) {
  const tasks = demoTasks.filter((task) => task.category === "followup" && (!taskId || task.id === taskId));
  const [selectedId, setSelectedId] = useState(taskId ?? tasks[0].id);
  const task = tasks.find((item) => item.id === selectedId) ?? tasks[0];
  const [dates, setDates] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState("");
  const promise = dates[task.id] ?? task.promise;
  return (
    <div className="task-demo__followup-layout">
      <Card>
        <CardHeader
          title="催票前，先确认承诺日期"
          description="跟进时间与供应商承诺分开记录，避免把等待天数当作超期。"
        />
        <CardContent>
          <FilterBar
            onSubmit={() =>
              setDraft(
                `${task.supplier}，您好：\n关于子采购单 ${task.order}（报关单 ${task.declaration}），当前尚待收票金额为 CNY ${task.outstanding}。\n请协助确认${promise ? `能否于 ${promise} 前完成开票` : "预计开票日期"}，并提供对应发票及明细。若开票安排有变化，请回复最新日期，谢谢。`,
              )
            }
            actions={<Button type="submit">预览催票草稿</Button>}
          >
            <Field label="跟进供应商" grow>
              <select
                value={task.id}
                disabled={Boolean(taskId)}
                onChange={(event) => {
                  setSelectedId(event.target.value);
                  setDraft("");
                }}
              >
                {tasks.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.supplier}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="承诺开票日期（演练填写）">
              <input
                type="date"
                value={promise}
                onChange={(event) => {
                  setDates((current) => ({ ...current, [task.id]: event.target.value }));
                  setDraft("");
                }}
              />
            </Field>
          </FilterBar>
          <dl className="task-demo__facts">
            <div>
              <dt>关联子采购单</dt>
              <dd>{task.order}</dd>
            </div>
            <div>
              <dt>待收票金额</dt>
              <dd>{task.outstanding} CNY</dd>
            </div>
            <div>
              <dt>原承诺日期</dt>
              <dd>{task.promise}</dd>
            </div>
            <div>
              <dt>原始样例状态</dt>
              <dd>
                <Badge tone={task.tone}>{task.timing}</Badge>
              </dd>
            </div>
            <div>
              <dt>最近联系</dt>
              <dd>{task.contact}</dd>
            </div>
          </dl>
          <Alert title="日期修改仅用于预览" tone="info">
            填写结果仅保留在当前演示视图。原始样例状态不会随日期变化重新判定，也不会保存或触发提醒。
          </Alert>
        </CardContent>
      </Card>
      <Card>
        <CardHeader
          title="供应商通知草稿"
          description="正式接入时，沿用现有通知预览与企微回执流程。"
          actions={<Badge tone="neutral">未发送</Badge>}
        />
        <CardContent>
          {draft ? (
            <label className="task-demo__note">
              预览内容
              <textarea readOnly rows={10} value={draft} />
            </label>
          ) : (
            <div className="task-demo__draft-placeholder">
              <strong>先核实日期，再组织催票内容</strong>
              <p>点击左侧“预览催票草稿”，查看带有采购单号、待收金额与承诺日期的通知。</p>
            </div>
          )}
          <p className="task-demo__muted">此示例不提供发送按钮；企微“已提交”和“已发送”仍需分别展示。</p>
        </CardContent>
      </Card>
    </div>
  );
}
