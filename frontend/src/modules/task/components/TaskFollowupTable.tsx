import { Link } from "react-router";
import { taskPath } from "../../../app/paths";
import { money } from "../../../shared/format/money";
import type { TaskGroup } from "../types/task";
import { formatTime } from "./format";
import "./task-followup-table.css";

const contactTime = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  })
    .format(new Date(value))
    .replace(/\//g, "-");

export function TaskFollowupTable({ groups }: { groups: TaskGroup[] }) {
  return (
    <div
      className="task-followup"
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- 键盘用户需要聚焦容器来横向滚动宽表。
      tabIndex={0}
      role="region"
      aria-label="开票跟进明细，可横向滚动"
    >
      <table>
        <colgroup>
          <col style={{ width: "22%" }} />
          <col style={{ width: "16%" }} />
          <col style={{ width: "12%" }} />
          <col style={{ width: "15%" }} />
          <col style={{ width: "13%" }} />
          <col style={{ width: "12%" }} />
          <col style={{ width: "10%" }} />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">供应商 / 经办人</th>
            <th scope="col">当前环节</th>
            <th scope="col" className="task-followup__amount">
              待收金额
            </th>
            <th scope="col">收票金额进度</th>
            <th scope="col">最近联系</th>
            <th scope="col">等待情况</th>
            <th scope="col">操作</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((group) =>
            group.tasks.map((task) => (
              <tr key={task.id}>
                <td>
                  <strong className="task-followup__supplier">{task.supplier}</strong>
                  <span className="task-followup__secondary">
                    {task.followupEmployee ? `通知经办：${task.followupEmployee}` : "经办人未提供"}
                    {" · "}
                    {task.company}
                  </span>
                </td>
                <td>
                  <span className="task-followup__status" data-status={task.status} title={task.reason}>
                    {task.statusLabel}
                  </span>
                  <span className="task-followup__secondary" title={task.orderNumbers.join("、")}>
                    {task.recordNumber || "报关单号缺失"}
                  </span>
                </td>
                <td className="task-followup__amount">
                  <strong>{task.outstandingAmount ? money(task.outstandingAmount) : "金额待确认"}</strong>
                  <span className="task-followup__secondary">{task.currency || "币种待确认"}</span>
                </td>
                <td>
                  {!task.receiptPercent || !task.receiptBarPercent ? (
                    <span className="task-followup__secondary">进度待确认</span>
                  ) : (
                    <div className="task-followup__progress">
                      <span className="task-followup__track" aria-hidden="true">
                        <span style={{ width: `${task.receiptBarPercent}%` }} />
                      </span>
                      <span aria-label={`收票金额进度 ${task.receiptPercent}%`}>{task.receiptPercent}%</span>
                    </div>
                  )}
                </td>
                <td>
                  {task.lastContactAt ? (
                    <time dateTime={task.lastContactAt} title={formatTime(task.lastContactAt)}>
                      {contactTime(task.lastContactAt)}
                    </time>
                  ) : (
                    <span className="task-followup__secondary">
                      {task.lastContactAt === undefined ? "联系记录待获取" : "暂无联系记录"}
                    </span>
                  )}
                </td>
                <td>
                  <span className="task-followup__waiting">{task.waitingLabel || "等待情况待获取"}</span>
                </td>
                <td>
                  <Link
                    className="ui-button ui-button--secondary"
                    to={taskPath(task.id)}
                    aria-label={`${task.supplier} ${task.recordNumber} 跟进详情`}
                  >
                    跟进详情
                  </Link>
                </td>
              </tr>
            )),
          )}
        </tbody>
      </table>
    </div>
  );
}
