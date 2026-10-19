import type { TaskCounts } from "../types/task";
import "./task-count-list.css";

export function TaskCountList({ counts }: { counts: TaskCounts }) {
  return (
    <dl className="task-counts">
      <div>
        <dt>待开票</dt>
        <dd>
          {counts.awaitingInvoice}
          <small> 个任务</small>
        </dd>
      </div>
      <div>
        <dt>已完成</dt>
        <dd>
          {counts.completed}
          <small> 个任务</small>
        </dd>
      </div>
      <div>
        <dt>待处理</dt>
        <dd>
          {counts.needsAttention}
          <small> 个任务</small>
        </dd>
      </div>
    </dl>
  );
}
