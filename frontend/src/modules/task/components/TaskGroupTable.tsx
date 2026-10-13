import { Link } from "react-router";
import { taskPath } from "../../../app/paths";
import type { TaskCounts, TaskGroup } from "../types/task";
import "./task-group-table.css";

export function TaskCountList({ counts }: { counts: TaskCounts }) {
  return (
    <dl className="it-counts">
      <div>
        <dt>待开票</dt>
        <dd>
          {counts.awaitingInvoice}
          <small> 个任务</small>
        </dd>
      </div>
      <div>
        <dt>已收票</dt>
        <dd>{counts.receivedInvoices === null ? "未接入" : `${counts.receivedInvoices} 张`}</dd>
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

export function TaskGroupTable({ group, first }: { group: TaskGroup; first: boolean }) {
  return (
    <details className="it-group" open={first}>
      <summary>
        <span className="it-group__title">
          <strong>{group.label}</strong>
          <span>
            {group.account} · {group.counts.tasks} 个任务
          </span>
        </span>
        <TaskCountList counts={group.counts} />
      </summary>
      <div
        className="it-table-wrap"
        // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 允许键盘用户聚焦并滚动宽表，保留原生表格语义。
        tabIndex={0}
        role="region"
        aria-label={`${group.label}的开票任务，可横向滚动`}
      >
        <table>
          <thead>
            <tr>
              <th>报关单 / 子采购单</th>
              <th>供应商 / 采购公司</th>
              <th>应开金额</th>
              <th>当前节点</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {group.tasks.map((task) => (
              <tr key={task.id}>
                <td>
                  <strong>{task.recordNumber || "报关单号缺失"}</strong>
                  <span className="it-secondary">{task.orderNumbers.join("、")}</span>
                </td>
                <td>
                  {task.supplier}
                  <span className="it-secondary">{task.company}</span>
                </td>
                <td>
                  {task.expectedAmount ?? "金额待确认"}
                  <span className="it-secondary">{task.currency || "来源未提供币种"}</span>
                </td>
                <td>
                  <span className="it-status">{task.statusLabel}</span>
                  <span className="it-secondary">
                    审核版本 {task.reviewRevision} · {task.lineCount} 行采购明细
                  </span>
                </td>
                <td>
                  <Link className="ui-button ui-button--secondary" to={taskPath(task.id)}>
                    查看节点
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}
